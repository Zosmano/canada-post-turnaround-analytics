"""End-to-end run: census + Canada Post data -> delivery plan -> address data -> CMB siting and
routing -> churn model -> dashboard.

    python run_all.py              # reuse cached extracts in data/ if present
    python run_all.py --rebuild    # re-read the census, Canada Post and ODA zips
    python run_all.py --dashboard  # only rebuild the dashboard from cached outputs
"""
import json
import sys
import time

import pandas as pd

from cpost import addresses, canadapost, census, churn, config as C, dashboard, delivery, nar, optimizer

N_REAL = 3
MIN_ODA_COVERAGE = 0.6


def pick_route_fsas(plan, profile, n=3):
    """Highest-priority reliable urban FSAs, one per province."""
    p = plan[(~plan.rural) & plan.data_reliable & (plan.door_points > 0)].sort_values("priority_rank")
    return p.drop_duplicates("province").head(n).merge(
        profile[["fsa", "dw_apt_5plus", "dw_apt_lt5"]], on="fsa")


def pick_real_fsas(plan, profile, ground, n=N_REAL):
    """Highest-priority FSAs whose address data covers enough of the FSA's ground-oriented homes."""
    p = plan.join(ground.rename("oda_ground"), on="fsa")
    p = p[(~p.rural) & p.data_reliable & (p.door_points > 0) & (p.oda_ground >= MIN_ODA_COVERAGE * p.ground_points)]
    p = p.sort_values("priority_rank")
    p = pd.concat([p.drop_duplicates("province"), p]).drop_duplicates("fsa").head(n)
    return p.merge(profile[["fsa", "dw_apt_5plus", "dw_apt_lt5"]], on="fsa")


def address_layer(plan, cp, rebuild=False):
    """Delivery locations, province by province: National Address Register if present, else ODA.

    Returns a summary, ground-oriented locations per FSA, geocoded depots and a loader for one FSA.
    """
    if nar.available():
        nar.build(force=rebuild)
        files, source = {f.name[:2]: f for f in sorted(nar.NAR_DIR.glob("*.csv.gz"))}, "NAR"
    else:
        addresses.build(force=rebuild)
        files, source = {f.name[:2]: f for f in sorted(addresses.ODA_DIR.glob("*.csv.gz"))}, "ODA"
    stats, provs, deps = [], [], []
    for pr, f in files.items():
        d = pd.read_csv(f, dtype=addresses.DTYPES)
        units = d.res_units if "res_units" in d else d.units
        mode = d.mode_type.notna() if "mode_type" in d else pd.Series(False, index=d.index)
        stats.append(pd.DataFrame({"fsa": d.fsa, "ground": d.kind == "ground", "units": units, "mode": mode})
                     .groupby("fsa").agg(ground_locations=("ground", "sum"), residential_units=("units", "sum"),
                                         locations=("ground", "size"), mode_rate=("mode", "mean")).assign(file=pr))
        provs.append({"province": pr, "locations": len(d), "addresses": int(d.units.sum()),
                      "residential_units": int(units.sum()), "postal_code_rate": float(d.postal_code.notna().mean()),
                      "mode_rate": float(mode.mean())})
        if cp is not None and "inst_pc" in d:
            inst = cp["inst"][cp["inst"].prov == pr]
            if len(inst):
                deps.append(canadapost.geocode_installations(inst, d))
    stats = pd.concat(stats).reset_index().sort_values("locations").drop_duplicates("fsa", keep="last").set_index("fsa")
    fcov = plan[["fsa", "province", "ground_points", "dwellings_total"]].join(stats, on="fsa")
    fcov["ground_coverage"] = fcov.ground_locations / fcov.ground_points
    fcov.round(3).to_csv(C.OUT_DIR / "address_fsa_coverage.csv", index=False)
    prov = pd.DataFrame(provs)
    summary = {"source": source, "has_boundary_file": addresses.boundary_file() is not None,
               "locations": int(prov.locations.sum()), "addresses": int(prov.addresses.sum()),
               "residential_units": int(prov.residential_units.sum()),
               "postal_match_rate": float((prov.mode_rate * prov.locations).sum() / prov.locations.sum()),
               "fsas_usable": int((fcov.ground_coverage >= MIN_ODA_COVERAGE).sum()),
               "provinces": prov.to_dict("records")}
    depots = pd.concat(deps, ignore_index=True) if deps else None
    if depots is not None:
        summary["depots"] = {"installations": int(len(depots)),
                             "address_matched": int(depots.geocode.fillna("").str.startswith("address match").sum()),
                             "centroid": int((depots.geocode == "centroid of served addresses").sum())}

    def load_fsa(fsa):
        d = pd.read_csv(files[stats.at[fsa, "file"]], dtype=addresses.DTYPES)
        return d[d.fsa == fsa].reset_index(drop=True)

    return summary, stats.ground_locations, depots, load_fsa


def load_cp(rebuild=False):
    return canadapost.build(force=rebuild) if canadapost.available() else None


def dashboard_only():
    """Rebuild outputs/dashboard.html from the cached outputs in seconds."""
    profile = census.build()
    cp = load_cp()
    plan, summary = delivery.run(profile, cp["fsa"] if cp else None)
    routes = json.loads((C.OUT_DIR / "route_optimization.json").read_text())
    metrics = json.loads((C.OUT_DIR / "churn_metrics.json").read_text())
    call = pd.read_csv(C.OUT_DIR / "churn_call_list.csv")
    oda = json.loads((C.OUT_DIR / "oda_summary.json").read_text())
    print("->", dashboard.build(profile, plan, summary, routes, metrics, call, oda))


def main():
    if "--dashboard" in sys.argv:
        return dashboard_only()
    t0 = time.time()
    rebuild = "--rebuild" in sys.argv
    print("1/6 Census profile and Canada Post data")
    profile = census.build(force=rebuild)
    cp = load_cp(rebuild)
    print("2/6 Delivery cost model and CMB conversion plan")
    plan, summary = delivery.run(profile, cp["fsa"] if cp else None)
    print(f"    door-to-door points {summary['door_points']:,.0f}, annual savings ${summary['annual_savings']/1e6:,.0f}M"
          f", delivery points from {summary['points_source']}")

    print("3/6 Address data")
    oda, ground, depots, load_fsa = address_layer(plan, cp, rebuild)
    print(f"    {oda['source']}: {oda['locations']:,} buildings/locations, {oda['addresses']:,} addresses, "
          f"{oda['fsas_usable']} FSAs with >= {MIN_ODA_COVERAGE:.0%} coverage, "
          f"{oda['postal_match_rate']:.0%} with a Canada Post delivery mode")
    if depots is not None:
        depots.to_csv(C.OUT_DIR / "depots.csv", index=False)
        oda["depots"] = {"installations": int(len(depots)),
                         "address_matched": int(depots.geocode.fillna("").str.startswith("address match").sum()),
                         "centroid": int((depots.geocode == "centroid of served addresses").sum())}
        print(f"    depots: {oda['depots']['address_matched']} of {len(depots)} installations geocoded by street address")
    (C.OUT_DIR / "oda_summary.json").write_text(json.dumps(oda, default=float))

    print("4/6 CMB siting and route optimization")
    routes = []
    cases = [("real", r) for _, r in pick_real_fsas(plan, profile, ground).iterrows()]
    cases += [("synthetic", r) for _, r in pick_route_fsas(plan, profile).iterrows()]
    for kind, row in cases:
        if kind == "real":
            dep = None
            if depots is not None and isinstance(row.get("cp_depot_pc"), str):
                hit = depots[(depots.inst_pc == row.cp_depot_pc) & depots.lat.notna()]
                if len(hit):
                    h = hit.iloc[0]
                    dep = {"lat": float(h.lat), "lon": float(h.lon), "name": row.cp_depot_name, "geocode": h.geocode}
            r = optimizer.optimize_real_fsa(row.to_dict(), load_fsa(row.fsa), depot=dep, source=f"{oda['source']} real addresses")
        else:
            r = optimizer.optimize_fsa(row.to_dict(), n_points=1500)
        r["annual_saving_fsa_top_down"] = float(row.annual_savings)
        routes.append(r)
        extra = (f", {r['cp_routes']['lc']} Canada Post LC routes = {r['model_hours_per_cp_route']:.1f} modelled h/route"
                 if "cp_routes" in r else "")
        print(f"    {r['fsa']} ({r['source']}): {r['cmb_sites_after']} CMB sites, daily cost "
              f"${r['before']['daily_cost']:,.0f} -> ${r['after']['daily_cost']:,.0f}, "
              f"FSA saving ${r['annual_saving_fsa_bottom_up']/1e6:.2f}M/yr (cost model ${row.annual_savings/1e6:.2f}M){extra}")
    (C.OUT_DIR / "route_optimization.json").write_text(json.dumps(routes, default=float))

    print("5/6 Business churn model")
    metrics, call = churn.run(profile)
    g = metrics["gbm"]
    print(f"    out-of-time AUC {g['auc']:.3f}, top-10% lift {g['lift_top10']:.1f}x, call list {len(call)} customers")
    print("6/6 Dashboard")
    path = dashboard.build(profile, plan, summary, routes, metrics, call, oda)
    print(f"Done in {time.time() - t0:.0f}s -> {path}")


if __name__ == "__main__":
    main()
