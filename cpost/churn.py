"""Business-customer churn early warning: who is about to move parcel volume to a competitor,
why, and which retention action is worth the most.

Data contract (swap the synthetic tables for CRM / billing extracts with the same columns):

customers: customer_id, segment, fsa, contract_type, renewal_month (1-12, or 0 for none),
           api_integrated (0/1), account_manager (0/1), discount_tier (0-3), tenure_months_at_start
monthly:   customer_id, month (YYYY-MM), parcels, revenue, on_time_pct, complaints, claims, rep_contact (0/1)

Churn label: parcels over the next 3 months fall below 10% of the trailing 12-month average.
That is the operational definition, so it applies equally to real data.

The synthetic generator reproduces the 2024-2026 disruption: national strike Nov-Dec 2024,
strike and rotating strikes Sept-Oct 2025, price increase Jan 2026. Customers are placed in
FSAs in proportion to the census count of self-employed, retail and wholesale workers.
THE SYNTHETIC CUSTOMERS ARE NOT REAL CANADA POST DATA.
"""
import json

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config as C

MONTHS = [str(p) for p in pd.period_range("2024-10", "2026-09", freq="M")]
STRIKE_INTENSITY = {"2024-11": 0.9, "2024-12": 0.8, "2025-09": 0.4, "2025-10": 0.6}
PRICE_INCREASE = "2026-01"
HORIZON = 3

SEGMENTS = {  # share, median monthly parcels, time sensitivity, price sensitivity, API adoption, $/parcel
    "ecommerce_smb":       (0.38, 120, 0.9, 0.6, 0.55, 13.5),
    "marketplace_seller":  (0.15, 60, 0.8, 0.8, 0.35, 12.0),
    "b2b_wholesale":       (0.20, 300, 0.5, 0.5, 0.40, 16.0),
    "retail_chain":        (0.07, 1500, 0.7, 0.4, 0.85, 11.0),
    "healthcare_pharma":   (0.08, 400, 0.6, 0.2, 0.60, 18.0),
    "government_nonprofit": (0.12, 200, 0.2, 0.2, 0.30, 15.0),
}


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def simulate(profile, n=C.N_BUSINESS_CUSTOMERS, seed=C.CHURN_SEED):
    rng = np.random.default_rng(seed)
    p = profile.dropna(subset=["self_employed"]).copy()
    w = (p.self_employed + p.ind_retail.fillna(0) + p.ind_wholesale.fillna(0)).clip(lower=0)
    fsa = rng.choice(p.fsa.values, size=n, p=(w / w.sum()).values)
    rural = pd.Series(fsa).str[1].eq("0").values

    names = list(SEGMENTS)
    seg_idx = rng.choice(len(names), size=n, p=[SEGMENTS[s][0] for s in names])
    par = np.array([SEGMENTS[s][1:] for s in names])[seg_idx]
    med_vol, time_sens, price_sens, api_p, unit_price = par.T
    base = med_vol * rng.lognormal(0, 1.0, n)
    tenure0 = rng.exponential(55, n).round() + 3

    contract = np.where(base > 800, np.where(rng.random(n) < 0.85, "commercial_contract", "small_business_program"),
                        np.where(rng.random(n) < 0.75, "small_business_program", "counter"))
    renewal = np.where(contract == "commercial_contract", rng.integers(1, 13, n), 0)
    api = rng.random(n) < api_p * np.where(base > 200, 1.0, 0.6)
    am = (base > 1200) & (rng.random(n) < 0.85)
    tier = np.digitize(base, [150, 600, 2000])
    price = unit_price * (1 - np.array([0, 0.05, 0.10, 0.18])[tier]) * rng.uniform(0.9, 1.1, n)
    wallet = np.where(rng.random(n) < 0.25, 0.6, 1.0)
    base_ot = 0.955 - 0.03 * rural + rng.normal(0, 0.01, n)

    alive = np.ones(n, bool)
    diss = np.zeros(n)
    gap = rng.integers(0, 12, n).astype(float)
    rows = []
    for m, month in enumerate(MONTHS):
        mo = int(month[-2:])
        inten = STRIKE_INTENSITY.get(month, 0.0)
        shock = 1.0 if month == PRICE_INCREASE else 0.0
        season = 1.3 if mo in (11, 12) else (0.88 if mo in (1, 2) else 1.0)
        on_time = np.clip(base_ot - 0.55 * inten + rng.normal(0, 0.015, n), 0.2, 0.995)
        complaints = rng.poisson(0.03 + 2.5 * (1 - on_time) * (base / 200) ** 0.3)
        claims = rng.poisson(0.01 * (base / 100) ** 0.5 * (1 + 3 * inten))
        contact = rng.random(n) < np.where(am, 0.55, 0.08)
        gap = np.where(contact, 0, gap + 1)
        diss = 0.65 * diss + 6 * np.maximum(0, 0.95 - on_time) + 0.25 * complaints

        erosion = inten * time_sens * 0.4 * rng.random(n) + shock * price_sens * 0.2 * rng.random(n)
        recover = np.where(on_time > 0.93, 0.04 * (1 - wallet), 0)
        wallet = np.clip(wallet * (1 - erosion) + recover, 0.05, 1.0)

        renewal_due = renewal == mo
        logit = (-5.2 +0.45 * diss + 1.4 * shock * price_sens + 1.6 * (1 - wallet) + 0.45 * ~api
                 + 0.35 * ~rural - 0.22 * np.log1p(tenure0 + m) + 1.1 * renewal_due - 0.7 * am
                 + 0.05 * np.minimum(gap, 12) + 1.2 * time_sens * inten)
        churn_now = alive & (rng.random(n) < _sigmoid(logit))
        live = alive & ~churn_now
        parcels = base * season * wallet * (1 - 0.7 * inten * time_sens) * rng.lognormal(0, 0.12, n)
        parcels = np.where(live, parcels, base * season * 0.02 * rng.random(n))
        alive = live
        rows.append(pd.DataFrame({
            "customer_id": np.arange(n), "month": month, "parcels": parcels.round(),
            "revenue": (parcels.round() * price).round(2), "on_time_pct": on_time.round(4),
            "complaints": complaints * live, "claims": claims * live, "rep_contact": contact.astype(int)}))

    customers = pd.DataFrame({
        "customer_id": np.arange(n), "segment": np.array(names)[seg_idx], "fsa": fsa,
        "contract_type": contract, "renewal_month": renewal, "api_integrated": api.astype(int),
        "account_manager": am.astype(int), "discount_tier": tier, "tenure_months_at_start": tenure0.astype(int)})
    return customers, pd.concat(rows, ignore_index=True)


# ------------------------------------------------------------------------------- features
NUMERIC = ["parcels_3m", "revenue_12m", "trend_3v12", "yoy_3m", "strike_dip", "strike_recovery",
           "post_price_change", "on_time_3m", "on_time_12m", "complaints_6m", "claims_6m",
           "months_since_complaint", "months_since_rep_contact", "tenure_months", "renewal_in_3m",
           "api_integrated", "account_manager", "discount_tier", "rural", "share_apartment", "share_work_home"]
CATEGORICAL = ["segment", "contract_type", "province"]

REASONS = {  # feature -> (plain-language reason, retention action)
    "on_time_3m": ("On-time delivery has slipped", "service_recovery"),
    "on_time_12m": ("Poor on-time record over the year", "service_recovery"),
    "complaints_6m": ("Recent complaints", "service_recovery"),
    "claims_6m": ("Loss or damage claims", "service_recovery"),
    "months_since_complaint": ("Complaint in the last few months", "service_recovery"),
    "strike_dip": ("Volume collapsed during the strike", "reliability_guarantee"),
    "strike_recovery": ("Volume has not come back since the strike", "reliability_guarantee"),
    "trend_3v12": ("Volume trending down", "reliability_guarantee"),
    "yoy_3m": ("Volume down year over year", "reliability_guarantee"),
    "post_price_change": ("Volume fell after the January price increase", "price_retention_offer"),
    "discount_tier": ("Low discount tier for its volume", "price_retention_offer"),
    "api_integrated": ("Not integrated by API (easy to switch)", "integration_support"),
    "renewal_in_3m": ("Contract renewal due within 3 months", "account_review"),
    "months_since_rep_contact": ("No sales contact for months", "account_review"),
}


def build_features(customers, monthly, profile, t_month, label=True):
    """Feature row per customer active at t_month, using history up to t_month only."""
    t = MONTHS.index(t_month) if t_month in MONTHS else sorted(monthly.month.unique()).index(t_month)
    months = sorted(monthly.month.unique())
    piv = lambda col: monthly.pivot(index="customer_id", columns="month", values=col).reindex(columns=months)
    P, R, OT, CP, CL, RC = (piv(c).values for c in ("parcels", "revenue", "on_time_pct", "complaints", "claims", "rep_contact"))
    ids = piv("parcels").index.values

    avg12 = P[:, max(0, t - 11):t + 1].mean(1)
    last3 = P[:, t - 2:t + 1].mean(1)
    active = last3 >= 0.1 * np.maximum(avg12, 1e-9)
    f = pd.DataFrame({"customer_id": ids})
    f["parcels_3m"] = last3
    f["revenue_12m"] = R[:, max(0, t - 11):t + 1].sum(1)
    f["trend_3v12"] = last3 / np.maximum(avg12, 1)
    f["yoy_3m"] = last3 / np.maximum(P[:, t - 14:t - 11].mean(1), 1) if t >= 14 else np.nan

    strike_idx = [i for i, m in enumerate(months) if m in STRIKE_INTENSITY and i <= t]
    if strike_idx:
        block = [i for i in strike_idx if i >= strike_idx[-1] - 1]
        pre = P[:, max(0, block[0] - 3):block[0]].mean(1) if block[0] > 0 else P[:, block].mean(1)
        f["strike_dip"] = P[:, block].min(1) / np.maximum(pre, 1)
        f["strike_recovery"] = last3 / np.maximum(pre, 1)
    else:
        f["strike_dip"] = f["strike_recovery"] = 1.0
    if PRICE_INCREASE in months and months.index(PRICE_INCREASE) <= t:
        k = months.index(PRICE_INCREASE)
        f["post_price_change"] = P[:, k:t + 1].mean(1) / np.maximum(P[:, max(0, k - 3):k].mean(1), 1)
    else:
        f["post_price_change"] = 1.0
    f["on_time_3m"] = OT[:, t - 2:t + 1].mean(1)
    f["on_time_12m"] = OT[:, max(0, t - 11):t + 1].mean(1)
    f["complaints_6m"] = CP[:, t - 5:t + 1].sum(1)
    f["claims_6m"] = CL[:, t - 5:t + 1].sum(1)
    hist = CP[:, :t + 1] > 0
    f["months_since_complaint"] = np.where(hist.any(1), t - (hist.shape[1] - 1 - hist[:, ::-1].argmax(1)), 24)
    rc = RC[:, :t + 1] > 0
    f["months_since_rep_contact"] = np.where(rc.any(1), t - (rc.shape[1] - 1 - rc[:, ::-1].argmax(1)), 24)

    f = f.merge(customers, on="customer_id", how="left")
    f["tenure_months"] = f.tenure_months_at_start + t
    mo = int(months[t][-2:])
    ahead = [((mo + k - 1) % 12) + 1 for k in range(1, HORIZON + 1)]
    f["renewal_in_3m"] = f.renewal_month.isin(ahead).astype(int)
    geo = profile.set_index("fsa")[["province", "rural", "share_apartment", "share_work_home"]]
    f = f.join(geo, on="fsa")
    f["rural"] = f.rural.astype(float)
    f["annual_revenue"] = f.revenue_12m
    f = f[active].copy()
    if label:
        if t + HORIZON >= len(months):
            raise ValueError(f"no label window after {t_month}")
        nxt = P[:, t + 1:t + 1 + HORIZON].mean(1)
        lab = pd.Series(nxt < 0.1 * np.maximum(avg12, 1e-9), index=ids)
        f["churn"] = f.customer_id.map(lab).astype(int)
    f["as_of"] = months[t]
    return f.reset_index(drop=True)


# ---------------------------------------------------------------------------------- model
def _X(df):
    X = df[NUMERIC + CATEGORICAL].copy()
    for c in CATEGORICAL:
        X[c] = X[c].astype("category")
    return X


def make_gbm():
    gbm = HistGradientBoostingClassifier(max_iter=500, learning_rate=0.04, max_leaf_nodes=31,
                                         l2_regularization=1.0, min_samples_leaf=40,
                                         categorical_features="from_dtype", random_state=0,
                                         early_stopping=True, validation_fraction=0.15, n_iter_no_change=30)
    return CalibratedClassifierCV(gbm, method="isotonic", cv=3)


def make_logit():
    pre = ColumnTransformer([("num", make_pipeline(StandardScaler()), NUMERIC),
                             ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL)])
    return make_pipeline(pre, LogisticRegression(max_iter=2000, C=0.5))


def _metrics(y, p, revenue):
    order = np.argsort(-p)
    k = max(1, int(0.1 * len(p)))
    top = order[:k]
    return {"auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)), "base_rate": float(y.mean()),
            "precision_top10": float(y[top].mean()), "lift_top10": float(y[top].mean() / y.mean()),
            "recall_top10": float(y[top].sum() / y.sum()),
            "revenue_captured_top10": float(revenue[top][y[top] == 1].sum() / revenue[y == 1].sum())}


def explain(model, X, ref, features=tuple(REASONS)):
    """Reason codes: drop in churn probability when each driver is reset to a healthy value."""
    base = model.predict_proba(X)[:, 1]
    drops = {}
    for f in features:
        Xh = X.copy()
        Xh[f] = ref[f]
        drops[f] = base - model.predict_proba(Xh)[:, 1]
    return pd.DataFrame(drops, index=X.index)


def run(profile, customers=None, monthly=None):
    C.OUT_DIR.mkdir(exist_ok=True)
    synthetic = customers is None
    if synthetic:
        customers, monthly = simulate(profile)
        customers.to_csv(C.DATA_DIR / "synthetic_customers.csv", index=False)
        monthly.to_csv(C.DATA_DIR / "synthetic_monthly.csv", index=False)

    train = pd.concat([build_features(customers, monthly, profile, m) for m in ("2025-12", "2026-01", "2026-02", "2026-03")])
    test = build_features(customers, monthly, profile, "2026-06")
    live = build_features(customers, monthly, profile, "2026-09", label=False)

    gbm, logit = make_gbm(), make_logit()
    gbm.fit(_X(train), train.churn)
    logit.fit(train[NUMERIC + CATEGORICAL].fillna(0), train.churn)
    p_gbm = gbm.predict_proba(_X(test))[:, 1]
    p_log = logit.predict_proba(test[NUMERIC + CATEGORICAL].fillna(0))[:, 1]
    y, rev = test.churn.values, test.annual_revenue.values
    metrics = {"synthetic_data": synthetic, "train_rows": int(len(train)), "test_rows": int(len(test)),
               "train_snapshots": ["2025-12", "2026-01", "2026-02", "2026-03"], "test_snapshot": "2026-06",
               "live_snapshot": "2026-09", "gbm": _metrics(y, p_gbm, rev), "logistic_baseline": _metrics(y, p_log, rev)}

    bins = pd.qcut(p_gbm, 10, labels=False, duplicates="drop")
    metrics["calibration"] = [{"predicted": float(p_gbm[bins == b].mean()), "observed": float(y[bins == b].mean())}
                              for b in np.unique(bins)]
    order = np.argsort(-p_gbm)
    metrics["gains"] = [{"pct_contacted": q, "pct_churners_caught": float(y[order[:int(q / 100 * len(y))]].sum() / y.sum())}
                        for q in range(0, 101, 5)]
    imp = permutation_importance(gbm, _X(test), y, scoring="roc_auc", n_repeats=4, random_state=0, n_jobs=1)
    metrics["importance"] = sorted(({"feature": f, "auc_drop": float(m)} for f, m in
                                    zip(NUMERIC + CATEGORICAL, imp.importances_mean)), key=lambda d: -d["auc_drop"])

    # Live scoring and the call list
    live["churn_prob"] = gbm.predict_proba(_X(live))[:, 1]
    live["revenue_at_risk"] = live.churn_prob * live.annual_revenue
    healthy = train[train.churn == 0]
    ref = {f: (healthy[f].median() if f not in ("api_integrated",) else 1) for f in REASONS}
    ref.update({"renewal_in_3m": 0, "months_since_rep_contact": 1, "months_since_complaint": 24,
                "complaints_6m": 0, "claims_6m": 0, "discount_tier": 3})
    top = live.sort_values("revenue_at_risk", ascending=False).head(600).copy()
    drops = explain(gbm, _X(top), ref)
    reasons, actions, values = [], [], []
    for i, row in drops.iterrows():
        best = row[row > 0.005].sort_values(ascending=False).head(3)
        reasons.append("; ".join(REASONS[f][0] for f in best.index) or "General risk profile")
        act = REASONS[best.index[0]][1] if len(best) else "account_review"
        actions.append(act)
        values.append(top.at[i, "churn_prob"] * top.at[i, "annual_revenue"] * C.SAVE_RATE[act] - C.INTERVENTION_COST[act])
    top["top_reasons"], top["recommended_action"], top["expected_value_of_action"] = reasons, actions, values
    cols = ["customer_id", "segment", "fsa", "province", "contract_type", "annual_revenue", "parcels_3m",
            "churn_prob", "revenue_at_risk", "top_reasons", "recommended_action", "expected_value_of_action",
            "on_time_3m", "complaints_6m", "strike_recovery", "trend_3v12", "renewal_in_3m", "api_integrated"]
    call = top[top.expected_value_of_action > 0].sort_values("expected_value_of_action", ascending=False)[cols]
    call.round(4).to_csv(C.OUT_DIR / "churn_call_list.csv", index=False)
    live[["customer_id", "segment", "fsa", "province", "annual_revenue", "churn_prob", "revenue_at_risk"]] \
        .round(4).to_csv(C.OUT_DIR / "churn_scores_all.csv", index=False)

    metrics["live"] = {"customers_scored": int(len(live)), "expected_churners_next_3m": float(live.churn_prob.sum()),
                       "revenue_at_risk": float(live.revenue_at_risk.sum()),
                       "call_list_size": int(len(call)), "call_list_expected_value": float(call.expected_value_of_action.sum()),
                       "by_segment": live.groupby("segment").agg(customers=("customer_id", "count"),
                                                                 mean_prob=("churn_prob", "mean"),
                                                                 revenue_at_risk=("revenue_at_risk", "sum"))
                       .reset_index().to_dict("records"),
                       "actions": call.recommended_action.value_counts().to_dict()}
    monthly_tot = monthly.groupby("month").agg(parcels=("parcels", "sum"), on_time=("on_time_pct", "mean")).reset_index()
    metrics["monthly_totals"] = monthly_tot.to_dict("records")
    (C.OUT_DIR / "churn_metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    return metrics, call
