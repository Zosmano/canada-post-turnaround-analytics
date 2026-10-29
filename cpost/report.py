"""Six report dashboards (KPI cards, side panel, titled chart cards) as 16:9 PNGs and one PDF, drawn from outputs/.

    python run_all.py --report     # redraw from the cached outputs in seconds
"""
import json
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Polygon

from cpost import config as C

# airmail palette, shared with the HTML dashboard: navy band, terracotta and indigo stripes on cream paper
BG, PAPER, CARD, EDGE, INK, MUTED, CHIP = "#EFE8D8", "#F7F2E7", "#FFFCF5", "#E0D6C1", "#1D2140", "#6A6C85", "#EFE7D6"
NAVY, INDIGO, TERRA, GOLD, GREEN, MIST = "#1E2350", "#3B4A9C", "#D4603F", "#B98B36", "#2F7D55", "#A9B3E0"
ICON = "Segoe MDL2 Assets"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "text.color": INK})
I = {"mail": "", "home": "", "building": "", "globe": "", "card": "", "trend": "",
     "history": "", "people": "", "chart": "", "check": "", "warn": "", "calc": "",
     "flag": "", "layers": "", "up": "", "down": "", "swap": "", "report": "",
     "lock": "", "pie": "", "chevron": ""}
# (page title, navigator icon, scope shown, data shown)
PAGES = [("Overview", "chart", "Both levers", "Q2 2026 + model"),
         ("Delivery network", "home", "Delivery cost", "1,646 FSAs"),
         ("Conversion plan", "flag", "Delivery cost", "1,646 FSAs"),
         ("Route optimizer", "globe", "Delivery cost", "3 real-street FSAs"),
         ("Parcel win-back", "people", "Parcel revenue", "Simulated customers"),
         ("Data & validation", "check", "Both levers", "All sources")]
FILES = ["P1_overview", "P2_delivery_network", "P3_conversion_plan", "P4_route_optimizer", "P5_parcel_winback", "P6_data_and_validation"]
R1 = [(0.135, 0.455, 0.274, 0.335), (0.4205, 0.455, 0.274, 0.335), (0.706, 0.455, 0.284, 0.335)]
R2 = [(0.135, 0.045, 0.415, 0.335), (0.561, 0.045, 0.429, 0.335)]
R3 = [(x, 0.045, w, h) for x, _, w, h in R1]
DISCLAIMER = "Independent analysis, not produced by or affiliated with Canada Post."


# ---------------------------------------------------------------------------------------- page furniture
def rbox(fig, x, y, w, h, fc=CARD, ec=EDGE, r=0.012, shadow=True):
    ax = fig.add_axes([x, y, w, h], zorder=-2)
    ax.axis("off")
    asp = (w * fig.get_figwidth()) / (h * fig.get_figheight())
    if shadow:
        ax.add_patch(FancyBboxPatch((0.004, -0.012), 1, 1, boxstyle=f"round,pad=0,rounding_size={r*3}", mutation_aspect=asp,
                                    transform=ax.transAxes, fc="#D9CDB4", ec="none", alpha=0.5, clip_on=False))
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle=f"round,pad=0,rounding_size={r*3}", mutation_aspect=asp,
                                transform=ax.transAxes, fc=fc, ec=ec, lw=0.9, clip_on=False))
    return ax


def airmail(fig, x, y, w, h, n=28):
    """Diagonal terracotta and indigo bars, the airmail envelope border."""
    ax = fig.add_axes([x, y, w, h], zorder=-1)
    ax.axis("off")
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    for i in range(n):
        col = (TERRA, PAPER, INDIGO, PAPER)[i % 4]
        ax.add_patch(Polygon([(i, 0), (i + 1, 0), (i + 1.6, 1), (i + 0.6, 1)], closed=True, fc=col, ec="none"))


def frame(page_no, kpis, source):
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    title, _, scope, shown = PAGES[page_no - 1]
    rbox(fig, 0.008, 0.02, 0.118, 0.96, fc=NAVY, ec=NAVY, shadow=False)
    airmail(fig, 0.008, 0.955, 0.118, 0.022, n=14)
    fig.text(0.067, 0.900, I["mail"], family=ICON, fontsize=30, color="#E9A58E", ha="center")
    fig.text(0.067, 0.866, "Canada Post", fontsize=11, weight="bold", color=PAPER, ha="center")
    fig.text(0.067, 0.848, "Turnaround Analytics", fontsize=8.6, color="#C3C6E0", ha="center")
    fig.text(0.067, 0.812, f"Page {page_no} of {len(PAGES)}", fontsize=7.5, color="#C3C6E0", ha="center")
    fig.text(0.067, 0.792, title, fontsize=10, weight="semibold", color="#F3C9B8", ha="center")
    boxes = [("Lever", scope), ("Geography", "Canada · 1,646 FSAs"), ("Data", shown), ("Snapshot", "Q2 2026")]
    for i, (lab, val) in enumerate(boxes):
        y = 0.70 - i * 0.085
        rbox(fig, 0.016, y, 0.102, 0.072, fc="#2A3066", ec="#3A4280", shadow=False)
        fig.text(0.024, y + 0.050, lab, fontsize=8, weight="semibold", color=PAPER)
        fig.text(0.024, y + 0.018, val, fontsize=7.4, color="#C3C6E0")
        for dy in (0.050, 0.018):
            fig.text(0.108, y + dy, I["chevron"], family=ICON, fontsize=7, color="#8E93C0", ha="center")
    for i, (_, ic, _, _) in enumerate(PAGES):
        cx, cy = (0.040, 0.093)[i % 2], 0.335 - (i // 2) * 0.078
        on = i == page_no - 1
        rbox(fig, cx - 0.021, cy - 0.031, 0.042, 0.062, fc=TERRA if on else "#2A3066", ec=TERRA if on else "#3A4280", r=0.03, shadow=False)
        fig.text(cx, cy + 0.002, I[ic], family=ICON, fontsize=15, color=PAPER if on else "#AEB3D8", ha="center", va="center")
        fig.text(cx, cy - 0.022, str(i + 1), fontsize=6.2, color=PAPER if on else "#8E93C0", ha="center")
    fig.text(0.067, 0.070, "Analysis and design by", fontsize=6.6, color="#C3C6E0", ha="center")
    fig.text(0.067, 0.050, "Osman Zakaria, PMP", fontsize=8.6, weight="bold", color="#F3C9B8", ha="center")
    fig.text(0.067, 0.031, "© 2026", fontsize=6.6, color="#C3C6E0", ha="center")
    x0, w, gap = 0.135, 0.1345, 0.0076
    for i, (ic, val, lab) in enumerate(kpis):
        x = x0 + i * (w + gap)
        rbox(fig, x, 0.875, w, 0.105, r=0.03)
        fig.text(x + 0.020, 0.938, I[ic], family=ICON, fontsize=19, color=INDIGO, ha="center", va="center")
        fig.text(x + 0.040, 0.937, val, fontsize=18, weight="bold", color=NAVY, va="center")
        fig.text(x + w / 2, 0.893, lab, fontsize=7.4, weight="semibold", color=MUTED, ha="center", va="center")
    fig.text(0.135, 0.008, f"{source} {DISCLAIMER}", fontsize=6.7, color=MUTED)
    return fig


def chart(fig, x, y, w, h, title, pl=0.0, pb=0.0):
    rbox(fig, x, y + h + 0.010, w, 0.040, r=0.006)
    fig.text(x + w / 2, y + h + 0.030, title, fontsize=8.8, weight="bold", color=NAVY, ha="center", va="center")
    rbox(fig, x, y, w, h, r=0.008)
    ax = fig.add_axes([x + 0.012 + pl, y + 0.045 + pb, w - 0.024 - pl, h - 0.075 - pb], zorder=2)
    ax.patch.set_alpha(0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, labelsize=7.6, colors=INK)
    ax.set_yticks([])
    return ax


# ---------------------------------------------------------------------------------------- chart kinds
def chip(ax, x, y, text, dy=0, fs=7.2):
    ax.annotate(text, (x, y), xytext=(0, 6 + dy), textcoords="offset points", ha="center", va="bottom", fontsize=fs,
                bbox=dict(boxstyle="round,pad=0.28,rounding_size=0.5", fc=CHIP, ec="none"))


def short(labels, n=12):
    return ["\n".join(textwrap.wrap(str(l), n, break_long_words=False)) for l in labels]


def legend(ax, names, colors):
    h = [plt.Line2D([], [], marker="o", ls="", ms=6, color=c, label=n) for n, c in zip(names, colors)]
    ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(names), frameon=False,
              fontsize=7.4, handletextpad=0.3, columnspacing=1.0, borderaxespad=0.2)


def vbar(ax, labels, vals, fmt="{:,.0f}", colors=INDIGO, wrap=11, fs=7.4):
    xs = range(len(vals))
    ax.bar(xs, vals, color=colors, width=0.62)
    for x, v in zip(xs, vals):
        chip(ax, x, max(v, 0), fmt.format(v), fs=6.8 if len(vals) > 10 else 7.2)
    lo = min(0, min(vals))
    ax.set_ylim(lo * 1.25, max(max(vals), 0) * 1.25 or 1)
    if lo < 0:
        ax.axhline(0, color="#D6CCB6", lw=1)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(short(labels, wrap), fontsize=fs)


def grouped(ax, cats, series, fmt="{:,.0f}", wrap=11):
    k = len(series)
    w = 0.8 / k
    allv = []
    for j, (_, vals, color) in enumerate(series):
        xs = [i - 0.4 + w * (j + 0.5) for i in range(len(cats))]
        ax.bar(xs, vals, width=w * 0.9, color=color)
        for x, v in zip(xs, vals):
            chip(ax, x, v, fmt.format(v), fs=6.6)
        allv += vals
    ax.set_ylim(0, max(allv) * 1.3)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(short(cats, wrap), fontsize=7.4)
    legend(ax, [s[0] for s in series], [s[2] for s in series])


def lines(ax, xs, series, xlabels=None, fmt=None, ylim=None):
    for name, ys, color, style in series:
        ax.plot(xs, ys, color=color, lw=2.2, ls=style, solid_capstyle="round")
    if ylim:
        ax.set_ylim(*ylim)
    ax.grid(axis="y", color="#EDE6D6", lw=0.8)
    ax.set_axisbelow(True)
    legend(ax, [s[0] for s in series], [s[2] for s in series])


def scatter(ax, x, y, color, xlabel, ylabel, logx=False, size=7):
    ax.scatter(x, y, s=size, color=color, alpha=0.45, edgecolors="none")
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel, fontsize=7.6, color=MUTED)
    ax.set_ylabel(ylabel, fontsize=7.6, color=MUTED)
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(color="#EDE6D6", lw=0.7)
    ax.set_axisbelow(True)


def money(v):
    return f"${v / 1e9:.2f}B" if abs(v) >= 1e9 else f"${v / 1e6:,.0f}M" if abs(v) >= 1e6 else f"${v / 1e3:,.0f}K"


# ---------------------------------------------------------------------------------------- the pages
def load():
    o = C.OUT_DIR
    return {"plan": pd.read_csv(o / "delivery_conversion_plan.csv"),
            "prov": pd.read_csv(o / "delivery_by_province.csv"),
            "summary": json.loads((o / "delivery_summary.json").read_text()),
            "routes": json.loads((o / "route_optimization.json").read_text()),
            "churn": json.loads((o / "churn_metrics.json").read_text()),
            "calls": pd.read_csv(o / "churn_call_list.csv"),
            "oda": json.loads((o / "oda_summary.json").read_text())}


def build(out_dir=None):
    out_dir = out_dir or C.OUT_DIR / "dashboards"
    d = load()
    plan, prov, S, routes, ch, calls, oda = d["plan"], d["prov"], d["summary"], d["routes"], d["churn"], d["calls"], d["oda"]
    Q = C.Q2_2026
    real = [r for r in routes if r["source"].startswith(("NAR", "ODA"))]
    prov = prov[prov.delivery_points > 0]
    figs = []

    # 1 Overview ------------------------------------------------------------------------------------
    g, live = ch["gbm"], ch["live"]
    fig = frame(1, [("card", money(S["annual_savings"]), "Annual delivery savings"), ("calc", money(S["capex"]), "One-time mailbox capital"),
                    ("history", f"{S['payback_years']:.1f} yrs", "Payback"), ("home", f"{S['door_points'] / 1e6:.1f}M", "Door-to-door addresses"),
                    ("layers", f"{S['cmb_sites_needed'] / 1e3:.1f}K", "Mailbox sites needed"), ("people", f"{g['lift_top10']:.1f}x", "Churn model lift, top 10%")],
                "Sources: Canada Post Q2 2026 report; delivery cost model on Canada Post 2017 data products and the 2021 Census.")
    vbar(chart(fig, *R1[0], "The size of the problem and the fix"),
         ["Segment loss, H1 2026", "Modelled annual savings", "Government estimate", "One-time capital"],
         [Q["segment_loss_before_tax_h1"] / 1e6, S["annual_savings"] / 1e6, C.PUBLISHED_ANNUAL_SAVINGS / 1e6, S["capex"] / 1e6],
         fmt="${:,.0f}M", colors=[TERRA, INDIGO, MIST, GOLD], wrap=12)
    vbar(chart(fig, *R1[1], "Q2 2026: parcels grow, mail shrinks (year on year)"),
         ["Parcel revenue", "Parcel volume", "Transaction mail revenue"],
         [100 * Q["parcel_revenue_growth_q2"], 100 * Q["parcel_volume_growth_q2"], 100 * Q["transaction_mail_revenue_growth_q2"]],
         fmt="{:+.1f}%", colors=[GREEN, GREEN, TERRA], wrap=12)
    w = S["waves"]
    grouped(chart(fig, *R1[2], "Three conversion waves, equal in size"), [f"Wave {k}" for k in w],
            [("Addresses (thousands)", [round(v["points"] / 1e3) for v in w.values()], INDIGO),
             ("Savings ($M a year)", [round(v["annual_savings"] / 1e6) for v in w.values()], TERRA)])
    p = prov.sort_values("annual_savings", ascending=False)
    vbar(chart(fig, *R2[0], "Annual savings by province ($M)"), p.province, p.annual_savings / 1e6, fmt="{:,.0f}",
         colors=[INDIGO if i < 2 else MIST for i in range(len(p))], wrap=6)
    vbar(chart(fig, *R2[1], "Addresses to convert: Canada Post's schedule vs the model's waves (thousands)"),
         ["Canada Post late 2026", "Canada Post 2027", "Model wave 1", "Model wave 2", "Model wave 3"],
         [Q["conversion_wave_late_2026"]["addresses"] / 1e3, Q["conversion_wave_2027"]["addresses"] / 1e3] + [v["points"] / 1e3 for v in w.values()],
         fmt="{:,.0f}K", colors=[GOLD, GOLD, INDIGO, INDIGO, INDIGO], wrap=12)
    figs.append(fig)

    # 2 Delivery network ----------------------------------------------------------------------------
    door_share = S["door_points"] / S["delivery_points"]
    fig = frame(2, [("globe", f"{S['fsas']:,}", "Forward sortation areas"), ("home", f"{S['delivery_points'] / 1e6:.1f}M", "Delivery points"),
                    ("mail", f"{door_share:.0%}", "Still door-to-door"), ("building", f"{S['business_points'] / 1e6:.1f}M", "Business points"),
                    ("swap", f"{S['cp_lc_routes']:,.0f}", "Letter-carrier routes"), ("flag", f"{S['rural_fsas']}", "Rural FSAs")],
                "Sources: Canada Post Householder and Delivery Mode Data (2017); 2021 Census Profile. Door-to-door calibrated to 4.0M (Q2 2026 report).")
    modes = [("Door-to-door", plan.door_points.sum(), TERRA), ("Community mailbox", plan.cmb_points_now.sum(), INDIGO),
             ("Apartment lobby", plan.apartment_points.sum(), MIST), ("Rural", plan.rural_points.sum(), GOLD),
             ("PO box", plan.po_box_points.sum(), GOLD), ("Business", plan.business_points.sum(), GREEN)]
    vbar(chart(fig, *R1[0], "Delivery points by mode (millions)"), [m[0] for m in modes], [m[1] / 1e6 for m in modes],
         fmt="{:.1f}M", colors=[m[2] for m in modes], wrap=10)
    urb = plan[~plan.rural & (plan.dwellings_total > 0)]
    bins = np.arange(0, 1.01, 0.1)
    cnt, _ = np.histogram(urb.door_share.clip(0, 0.999), bins)
    vbar(chart(fig, *R1[1], "Urban FSAs by share still door-to-door"), [f"{int(b * 100)}–{int(b * 100) + 10}%" for b in bins[:-1]], cnt,
         colors=[TERRA if b >= 0.5 else INDIGO for b in bins[:-1]], wrap=8, fs=6.6)
    p = prov.sort_values("door_points", ascending=False)
    vbar(chart(fig, *R1[2], "Door-to-door addresses by province (thousands)"), p.province, p.door_points / 1e3, fmt="{:,.0f}",
         colors=[TERRA if i < 2 else INDIGO for i in range(len(p))], wrap=6)
    ax = chart(fig, *R2[0], "How the model assigns door delivery: by share of homes built before 1981", pl=0.035, pb=0.03)
    scatter(ax, urb.share_pre1981 * 100, urb.door_share * 100, INDIGO, "Homes built before 1981 (%)", "Door-to-door (%)")
    r = np.corrcoef(urb.share_pre1981.fillna(0), urb.door_share)[0, 1]
    ax.text(0.02, 0.95, f"{len(urb):,} urban FSAs. Construction age is a model input (calibrated to 4.0M door addresses),\nso this shows the assumption, not an independent finding (r = {r:.2f}).",
            transform=ax.transAxes, fontsize=7.2, color=MUTED, va="top")
    ax = chart(fig, *R2[1], "Door delivery by density (dwellings per km², log scale)", pl=0.035, pb=0.03)
    dd = urb[urb.dwellings_per_km2 > 0]
    scatter(ax, dd.dwellings_per_km2, dd.door_share * 100, TERRA, "Dwellings per km²", "Door-to-door (%)", logx=True)
    figs.append(fig)

    # 3 Conversion plan -----------------------------------------------------------------------------
    w1 = S["waves"]["1"]
    pr = plan[plan.priority_rank.notna()].sort_values("priority_rank")
    cum = pr.annual_savings.cumsum() / pr.annual_savings.sum()
    half = int((cum < 0.5).sum()) + 1
    fig = frame(3, [("flag", f"{w1['fsas']}", "Wave 1 FSAs"), ("card", money(w1["annual_savings"]), "Wave 1 savings a year"),
                    ("trend", f"{half}", "FSAs for half the savings"), ("warn", f"{S['equity_flag_fsas']}", "FSAs flagged for equity review"),
                    ("people", f"{S['accommodated_points']:,.0f}", "Homes kept on door delivery"), ("history", f"{S['payback_years']:.1f} yrs", "Payback, every FSA")],
                "Sources: delivery cost model; equity flags from 2021 Census age and low-income shares; accommodation scaled from the 18,000-household program.")
    p = prov.sort_values("annual_savings", ascending=False).head(8)
    grouped(chart(fig, *R1[0], "Savings a year vs one-time capital, top 8 provinces ($M)"), p.province,
            [("Savings a year", list((p.annual_savings / 1e6).round()), INDIGO), ("Capital", list((p.capex / 1e6).round()), GOLD)], wrap=6)
    xs = np.linspace(0, 100, 51)
    ys = np.interp(xs, 100 * np.arange(1, len(cum) + 1) / len(cum), 100 * cum.values)
    ax = chart(fig, *R1[1], "Savings captured as FSAs convert in priority order (%)", pb=0.02)
    lines(ax, xs, [("Priority order", ys, TERRA, "-"), ("Equal spread", xs, MIST, "--")], ylim=(0, 105))
    ax.set_xlabel("FSAs converted (%)", fontsize=7.6, color=MUTED)
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.set_yticks([0, 25, 50, 75, 100])
    eq = plan[plan.equity_flag].groupby("province").size().sort_values(ascending=False)
    vbar(chart(fig, *R1[2], "FSAs flagged for equity review, by province"), eq.index, eq.values, colors=TERRA, wrap=6)
    top = pr.head(15)
    vbar(chart(fig, *R2[0], "The 15 highest-priority FSAs: savings a year ($M)"), top.fsa, top.annual_savings / 1e6, fmt="{:.2f}",
         colors=[INDIGO if wv == 1 else MIST for wv in top.wave], wrap=5, fs=7)
    wv = plan[plan.wave.notna()].groupby("wave").agg(fsas=("fsa", "size"), per=("annual_savings", "median"))
    grouped(chart(fig, *R2[1], "Wave sizes: FSAs per wave and median savings per FSA ($K)"), [f"Wave {int(k)}" for k in wv.index],
            [("FSAs", list(wv.fsas), INDIGO), ("Median savings per FSA ($K)", list((wv.per / 1e3).round()), TERRA)])
    figs.append(fig)

    # 4 Route optimizer -----------------------------------------------------------------------------
    t2j = real[0]
    cut = 1 - t2j["after"]["daily_cost"] / t2j["before"]["daily_cost"]
    fig = frame(4, [("globe", f"{len(real)}", "Real-street case FSAs"), ("down", f"{cut:.0%}", f"{t2j['fsa']} daily cost cut"),
                    ("layers", f"{t2j['cmb_sites_after']}", f"Mailbox sites in {t2j['fsa']}"),
                    ("people", f"{t2j['mean_walk_to_cmb_m']:.0f} m", "Average walk to a mailbox"),
                    ("swap", f"{t2j['road_network']['segments']:,}", f"Road segments, {t2j['fsa']}"),
                    ("history", f"{t2j['model_hours_per_cp_route']:.1f} h", "Modelled hours per route")],
                "Sources: National Address Register and 2021 Road Network File; Canada Post depots and routes. Capacitated mailbox siting, then Clarke-Wright routing with 2-opt.")
    names = [f"{r['fsa']} ({r['province']})" for r in real]
    grouped(chart(fig, *R1[0], "Daily delivery cost, before vs after ($)"), names,
            [("Before", [round(r["before"]["daily_cost"]) for r in real], TERRA), ("After", [round(r["after"]["daily_cost"]) for r in real], INDIGO)])
    grouped(chart(fig, *R1[1], "Carrier hours a day, before vs after"), names,
            [("Before", [round(r["before"]["walk_hours"] + r["before"]["drive_hours"]) for r in real], TERRA),
             ("After", [round(r["after"]["drive_hours"]) for r in real], INDIGO)])
    grouped(chart(fig, *R1[2], "Vehicle kilometres a day, before vs after"), names,
            [("Before", [round(r["before"]["vehicle_km"]) for r in real], TERRA), ("After", [round(r["after"]["vehicle_km"]) for r in real], INDIGO)])
    ax = chart(fig, *R2[0], f"{t2j['fsa']}, Calgary (one neighbourhood): door routes today and the mailbox sites that replace them")
    pts = np.array(t2j["plot"]["points"]["door"])
    cx, cy = np.median(pts, axis=0)
    hw, hh = 1150, 480                      # a 2.3 km x 1 km window, matching the card's shape
    inside = lambda a: (abs(a[:, 0] - cx) < hw) & (abs(a[:, 1] - cy) < hh)
    for rt in t2j["plot"]["routes_before_walk"]:
        a = np.array(rt[1:-1]) if len(rt) > 2 else np.array(rt)
        if len(a) > 1 and inside(a).any():
            ax.plot(a[:, 0], a[:, 1], color=TERRA, lw=0.8, alpha=0.55)
    ax.scatter(pts[:, 0], pts[:, 1], s=4, color="#B5AE9C", edgecolors="none")
    st = np.array(t2j["plot"]["sites_after"])
    ax.scatter(st[:, 0], st[:, 1], s=st[:, 2] * 2.2, color=INDIGO, alpha=0.9, edgecolors=CARD, linewidths=0.6, zorder=3)
    ax.set_xlim(cx - hw, cx + hw)
    ax.set_ylim(cy - hh, cy + hh)
    ax.set_xticks([])
    ax.text(0.99, -0.07, "Window 2.3 km × 1 km; circle size = homes served", transform=ax.transAxes, ha="right", fontsize=6.8, color=MUTED)
    legend(ax, ["Door homes", "Walking routes today", "New mailbox sites"], ["#B5AE9C", TERRA, INDIGO])
    grouped(chart(fig, *R2[1], "Walk from home to the new mailbox (metres)"), names,
            [("Average", [round(r["mean_walk_to_cmb_m"]) for r in real], INDIGO), ("Longest", [round(r["max_walk_to_cmb_m"]) for r in real], GOLD)])
    figs.append(fig)

    # 5 Parcel win-back -----------------------------------------------------------------------------
    drop = prov.est_parcel_drop_2025.sum()
    fig = frame(5, [("people", f"{live['customers_scored']:,}", "Customers scored (simulated)"),
                    ("warn", f"{live['expected_churners_next_3m']:.0f}", "Expected to leave in 3 months"),
                    ("card", money(live["revenue_at_risk"]), "Revenue at risk"), ("report", f"{live['call_list_size']}", "Customers on the call list"),
                    ("chart", f"{g['auc']:.2f}", "Model AUC, out of time"), ("down", f"{drop / 1e6:.0f}M", "2025 parcel drop to win back")],
                "Churn results use SIMULATED customers (Canada Post customer data is not public) and show the method, not real churn. "
                "The 2025 parcel drop is allocated to FSAs by modelled parcel demand.")
    gains = ch["gains"]
    ax = chart(fig, *R1[0], "Gains: share of leavers caught by calling the riskiest customers (%)", pb=0.02)
    lines(ax, [x["pct_contacted"] for x in gains], [("Model", [100 * x["pct_churners_caught"] for x in gains], INDIGO, "-"),
                                                   ("Random calls", [x["pct_contacted"] for x in gains], MIST, "--")], ylim=(0, 105))
    ax.set_xlabel("Customers contacted (%)", fontsize=7.6, color=MUTED)
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.set_yticks([0, 25, 50, 75, 100])
    lb = ch["logistic_baseline"]
    ms = [("AUC", "auc"), ("PR-AUC", "pr_auc"), ("Leavers caught, top 10%", "recall_top10"), ("Revenue caught, top 10%", "revenue_captured_top10")]
    grouped(chart(fig, *R1[1], "Gradient boosting vs logistic baseline (%)"), [m[0] for m in ms],
            [("Gradient boosting", [round(100 * g[k]) for _, k in ms], INDIGO), ("Logistic", [round(100 * lb[k]) for _, k in ms], MIST)], wrap=12)
    imp = ch["importance"][:6]
    lab = {"trend_3v12": "Volume trend (3 vs 12 months)", "discount_tier": "Discount tier", "revenue_12m": "Revenue, 12 months",
           "months_since_complaint": "Months since complaint", "post_price_change": "After a price change", "yoy_3m": "Year-on-year volume"}
    vbar(chart(fig, *R1[2], "What predicts leaving (AUC lost without it, points)"), [lab.get(x["feature"], x["feature"]) for x in imp],
         [100 * x["auc_drop"] for x in imp], fmt="{:.1f}", colors=[TERRA] + [INDIGO] * 5, wrap=11)
    seg = sorted(live["by_segment"], key=lambda s: -s["revenue_at_risk"])
    vbar(chart(fig, *R3[0], "Revenue at risk by customer segment ($K)"), [s["segment"].replace("_", " ").capitalize() for s in seg],
         [s["revenue_at_risk"] / 1e3 for s in seg], fmt="{:,.0f}", colors=[TERRA] + [INDIGO] * 5, wrap=10)
    act = live["actions"]
    vbar(chart(fig, *R3[1], "Recommended retention action (call list)"), [k.replace("_", " ").capitalize() for k in act], list(act.values()),
         colors=[INDIGO, TERRA, GOLD, MIST], wrap=11)
    p = prov.sort_values("est_parcel_drop_2025", ascending=False)
    vbar(chart(fig, *R3[2], "2025 parcel drop to win back, by province (millions)"), p.province, p.est_parcel_drop_2025 / 1e6, fmt="{:.1f}",
         colors=[TERRA if i < 2 else INDIGO for i in range(len(p))], wrap=6, fs=7)
    figs.append(fig)

    # 6 Data & validation ---------------------------------------------------------------------------
    dep = oda["depots"]
    over = S["annual_savings"] / C.PUBLISHED_ANNUAL_SAVINGS - 1
    fig = frame(6, [("building", f"{oda['locations'] / 1e6:.1f}M", "Buildings in the address register"), ("home", f"{oda['addresses'] / 1e6:.1f}M", "Addresses"),
                    ("check", f"{oda['postal_match_rate']:.1%}", "Matched to a delivery mode"), ("globe", f"{oda['fsas_usable']:,}", "FSAs with usable addresses"),
                    ("mail", f"{dep['address_matched']:,}", f"Depots located by address (of {dep['installations']:,})"),
                    ("up", f"{over:+.0%}", "Savings vs government estimate")],
                "Sources: StatCan National Address Register (46-26-0002) and 2021 Road Network File; Canada Post Householder, Delivery Mode and Postal Code Address Data (2017).")
    names = [r["fsa"] for r in real]
    grouped(chart(fig, *R1[0], "Two independent models agree: annual savings per FSA ($M)"), names,
            [("Route model, real streets", [round(r["annual_saving_fsa_bottom_up"] / 1e6, 2) for r in real], INDIGO),
             ("Unit-cost model", [round(r["annual_saving_fsa_top_down"] / 1e6, 2) for r in real], GOLD)], fmt="{:.2f}")
    vbar(chart(fig, *R1[1], "National savings: model vs government estimate ($M)"), ["This model", "Government estimate"],
         [S["annual_savings"] / 1e6, C.PUBLISHED_ANNUAL_SAVINGS / 1e6], fmt="${:,.0f}M", colors=[INDIGO, MIST], wrap=12)
    vbar(chart(fig, *R1[2], "Modelled delivery hours per Canada Post route (real streets)"), names,
         [r["model_hours_per_cp_route"] for r in real], fmt="{:.1f} h", colors=TERRA, wrap=8)
    pv = pd.DataFrame(oda["provinces"]).sort_values("locations", ascending=False)
    vbar(chart(fig, *R2[0], "Buildings matched to a Canada Post delivery mode, by province (%)"), pv.province, 100 * pv.mode_rate, fmt="{:.1f}",
         colors=[TERRA if r < 0.97 else INDIGO for r in pv.mode_rate], wrap=6, fs=7)
    other = dep["installations"] - dep["address_matched"] - dep["centroid"]
    vbar(chart(fig, *R2[1], "How the 4,797 delivery installations were located"),
         ["Street-address match", "Centroid of served addresses", "Not located"],
         [dep["address_matched"], dep["centroid"], other], colors=[INDIGO, GOLD, MIST], wrap=14)
    figs.append(fig)

    out_dir.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_dir / "canada_post_turnaround_dashboards.pdf") as pdf:
        for f, name in zip(figs, FILES):
            f.savefig(out_dir / f"{name}.png", dpi=220, facecolor=BG)
            pdf.savefig(f, facecolor=BG)
            plt.close(f)
    return [out_dir / f"{n}.png" for n in FILES]


if __name__ == "__main__":
    print(build())
