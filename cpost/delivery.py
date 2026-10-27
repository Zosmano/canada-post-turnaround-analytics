"""Delivery-network cost model and community-mailbox (CMB) conversion plan per FSA.

For each FSA the model estimates delivery points by mode (door-to-door, CMB, lobby, rural)
from the census dwelling mix and construction period, calibrates door-to-door volume to the
national total, then sizes the conversion: points converted, accommodation exemptions,
annual savings, capital cost, payback, CMB sites needed and a rollout wave.

It also scores every FSA for parcel demand and allocates the 2025 drop in parcel volume across
FSAs by that demand, so sales can set win-back targets by territory.
"""
import json

import numpy as np
import pandas as pd

from . import config as C

# Canada Post 2025 annual results: parcel volume fell 79 million pieces (32.6%) from 2024, as customers
# moved volume to other carriers during the labour disruption. Allocated to FSAs by modelled demand.
PARCEL_VOLUME_DROP_2025 = 79_000_000
PARCEL_VOLUME_DROP_PCT_2025 = 0.326


def unit_costs():
    return dict(C.COST_PER_POINT)


def _door_propensity(d):
    """Relative chance a door-eligible point is still door-to-door, from its construction period."""
    w = C.DOOR_PROPENSITY
    return (w["pre1981"] * d.share_pre1981.fillna(0) + w["1981_1990"] * d.share_1981_1990.fillna(0)
            + w["post1990"] * d.share_post1990.fillna(0))


def calibrate_door_factor(d):
    """Scale k so that sum(candidates x min(1, k x propensity)) hits the national total (bisection)."""
    prop = _door_propensity(d)
    total = lambda k: (d.door_candidates * np.minimum(1, k * prop)).sum()
    lo, hi = 0.0, 50.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if total(mid) < C.NATIONAL_DOOR_POINTS_TARGET else (lo, mid)
    return (lo + hi) / 2


def delivery_points(d, cp_fsa=None):
    """Residential delivery points by mode.

    Canada Post Householder counts (Total Points of Call) where the FSA appears in them:
    door-eligible = letter-carrier houses + duplex flats; lobby = other letter-carrier apartments;
    suburban service, lock box and other modes are already centralized; rural routes are rural.
    Census dwellings otherwise (FSAs created after 2017).
    """
    d["census_dwellings"] = d.dwellings_total
    d["points_source"] = "census"
    for col in ("business_points", "po_box_points", "cp_lc_routes", "cp_ss_routes", "cp_rr_routes"):
        d[col] = np.nan if col.startswith("cp_") else 0.0
    d["ground_points"] = d.dwellings_total * d.share_ground.fillna(1)
    d["apartment_points"] = d.dwellings_total - d.ground_points
    d["door_candidates"] = np.where(d.rural, 0.0, d.ground_points)
    d["rural_points"] = np.where(d.rural, d.ground_points, 0.0)
    if cp_fsa is None:
        return d
    d = d.drop(columns=["cp_lc_routes", "cp_ss_routes", "cp_rr_routes"]).merge(cp_fsa, on="fsa", how="left")
    has = d.cp_points_total.fillna(0) > 0
    apts = (d.dw_duplex + d.dw_apt_lt5 + d.dw_apt_5plus).replace(0, np.nan)
    duplex = (d.cp_lc_apt * (d.dw_duplex / apts).fillna(0))
    cand = d.cp_lc_house + duplex
    res = cand + (d.cp_lc_apt - duplex) + d.cp_ss_res + d.cp_lb_res + d.cp_other_res + d.cp_rr_res
    d.loc[has, "points_source"] = "Canada Post 2017"
    d.loc[has, "door_candidates"] = cand[has]
    d.loc[has, "ground_points"] = (cand + d.cp_ss_res)[has]
    d.loc[has, "apartment_points"] = (d.cp_lc_apt - duplex)[has]
    d.loc[has, "rural_points"] = d.cp_rr_res[has]
    d.loc[has, "po_box_points"] = (d.cp_lb_res + d.cp_other_res)[has]
    d.loc[has, "business_points"] = d.cp_business[has]
    d.loc[has, "dwellings_total"] = res[has]
    return d


def build_plan(profile, cp_fsa=None):
    d = profile.copy()
    d = d[d.dwellings_total.fillna(0) > 0].copy()
    d = delivery_points(d, cp_fsa)

    k = calibrate_door_factor(d)
    d["door_share"] = np.minimum(1, k * _door_propensity(d))
    d["door_points"] = d.door_candidates * d.door_share
    d["cmb_points_now"] = (d.ground_points - d.door_points - np.where(d.points_source == "census", d.rural_points, 0)).clip(lower=0)

    # Accommodation: today's program size (Q2 2026 report) relative to the households already on
    # centralized delivery, scaled by each FSA's share of maintainers aged 75+
    centralized = d.dwellings_total.sum() - d.door_points.sum()
    base = C.ACCOMMODATION_PROGRAM_HOUSEHOLDS / centralized * C.ACCOMMODATION_UPLIFT
    old = ((d.maint_75_84 + d.maint_85_plus) / d.maint_total.replace(0, np.nan)).fillna(0)
    d["accommodation_share"] = (base * old / max(old.mean(), 1e-9)).clip(0, 1)
    d["accommodated_points"] = d.door_points * d.accommodation_share
    d["convertible_points"] = d.door_points - d.accommodated_points

    c = unit_costs()
    d["annual_cost_now"] = (d.door_points * c["door"] + (d.cmb_points_now + d.po_box_points) * c["cmb"]
                            + d.rural_points * c["rural"] + d.apartment_points * c["lobby"])
    d["annual_savings"] = d.convertible_points * (c["door"] - c["cmb"])
    d["capex"] = d.convertible_points * C.CMB_CAPEX_PER_POINT
    d["payback_years"] = d.capex / d.annual_savings.replace(0, np.nan)
    d["cmb_sites_needed"] = np.ceil(d.convertible_points / C.CMB_SITE_CAPACITY)

    # Equity: older and lower-income areas need in-person engagement before conversion
    q65, qli = d.share_65_plus.quantile(0.75), d.low_income_pct.quantile(0.75)
    d["equity_flag"] = (d.share_65_plus > q65) & (d.low_income_pct > qli)
    d["readiness"] = (1 - 0.6 * d.accommodation_share - 0.2 * d.equity_flag).clip(0, 1)
    d["priority_score"] = d.annual_savings * d.readiness

    conv = d[d.convertible_points > 0].sort_values("priority_score", ascending=False)
    cum = conv.convertible_points.cumsum() / conv.convertible_points.sum()
    d["wave"] = pd.Series(np.minimum(np.ceil(cum * C.CONVERSION_WAVES), C.CONVERSION_WAVES), index=conv.index)
    d["priority_rank"] = d.priority_score.rank(ascending=False, method="first")

    # Parcel demand: households x relative income x at-home and education propensities
    nat_inc = np.nanmedian(d.median_hh_income)
    demand = (d.dwellings_occupied * (d.median_hh_income.fillna(nat_inc) / nat_inc) ** 0.8
              * (1 + d.share_work_home.fillna(0)) * (1 + 0.5 * d.share_bachelor.fillna(0)))
    d["parcel_demand_share"] = demand / demand.sum()
    d["est_parcel_drop_2025"] = d.parcel_demand_share * PARCEL_VOLUME_DROP_2025
    # Screening only: 2016 counts are blank for FSAs (boundaries changed), so vacancy stands in for decline
    vacancy = d.vacant_dwellings / d.dwellings_total
    d["rural_review_score"] = np.where(
        d.rural, _z(vacancy.fillna(0)) + _z(d.share_65_plus.fillna(0)) + _z(-np.log1p(d.pop_2021.fillna(0))), np.nan)
    return d, {"door_factor": k, "pre1981_door_share": float(min(1, k * C.DOOR_PROPENSITY["pre1981"])),
               "accommodation_base_rate": base, "unit_costs": c}


def _z(s):
    return (s - s.mean()) / (s.std() or 1)


def summarize(d, calib):
    s = {
        "fsas": int(len(d)), "rural_fsas": int(d.rural.sum()),
        "delivery_points": float(d.dwellings_total.sum()),
        "door_points": float(d.door_points.sum()),
        "accommodated_points": float(d.accommodated_points.sum()),
        "convertible_points": float(d.convertible_points.sum()),
        "annual_cost_now": float(d.annual_cost_now.sum()),
        "annual_savings": float(d.annual_savings.sum()),
        "capex": float(d.capex.sum()),
        "payback_years": float(d.capex.sum() / d.annual_savings.sum()),
        "cmb_sites_needed": float(d.cmb_sites_needed.sum()),
        "equity_flag_fsas": int(d.equity_flag.sum()),
        "pre1981_door_share": calib["pre1981_door_share"],
        "accommodation_base_rate": calib["accommodation_base_rate"],
        "unit_costs": calib["unit_costs"],
        "points_source": d.points_source.value_counts().to_dict(),
        "business_points": float(d.business_points.sum()),
        "cp_lc_routes": float(d.cp_lc_routes.sum()) if d.cp_lc_routes.notna().any() else None,
        "waves": {int(w): {"fsas": int(len(g)), "points": float(g.convertible_points.sum()),
                           "annual_savings": float(g.annual_savings.sum())}
                  for w, g in d.dropna(subset=["wave"]).groupby("wave")},
    }
    return s


def province_summary(d):
    g = d.groupby("province").agg(
        fsas=("fsa", "count"), delivery_points=("dwellings_total", "sum"), door_points=("door_points", "sum"),
        convertible_points=("convertible_points", "sum"), annual_savings=("annual_savings", "sum"),
        capex=("capex", "sum"), cmb_sites_needed=("cmb_sites_needed", "sum"),
        est_parcel_drop_2025=("est_parcel_drop_2025", "sum"))
    return g.sort_values("annual_savings", ascending=False).reset_index()


PLAN_COLS = ["fsa", "province", "rural", "pop_2021", "points_source", "census_dwellings", "dwellings_total",
             "ground_points", "apartment_points", "door_candidates", "door_share", "door_points", "cmb_points_now",
             "rural_points", "po_box_points", "business_points", "cp_lc_routes", "cp_ss_routes", "cp_rr_routes",
             "cp_depot_pc", "cp_depot_name", "accommodation_share", "accommodated_points",
             "convertible_points", "annual_cost_now", "annual_savings", "capex", "payback_years",
             "cmb_sites_needed", "equity_flag", "share_65_plus", "low_income_pct", "share_pre1981",
             "readiness", "priority_score", "priority_rank", "wave", "parcel_demand_share",
             "est_parcel_drop_2025", "rural_review_score", "data_reliable"]


def run(profile, cp_fsa=None):
    C.OUT_DIR.mkdir(exist_ok=True)
    d, calib = build_plan(profile, cp_fsa)
    cols = [c for c in PLAN_COLS if c in d.columns] + [c for c in ("land_area_km2", "dwellings_per_km2") if c in d.columns]
    d.sort_values("priority_rank")[cols].round(4).to_csv(C.OUT_DIR / "delivery_conversion_plan.csv", index=False)
    province_summary(d).round(0).to_csv(C.OUT_DIR / "delivery_by_province.csv", index=False)
    s = summarize(d, calib)
    (C.OUT_DIR / "delivery_summary.json").write_text(json.dumps(s, indent=2))
    return d, s
