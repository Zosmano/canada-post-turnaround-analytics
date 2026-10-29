"""Extract the 2021 Census Profile into analysis-ready tables.

* fsa_profile.csv  one row per FSA (~1,640), ~80 columns, from the full FSA profile
                   plus 95% confidence intervals from the FSA CI file
* cma_context.csv  full-time employment income with 95% CIs for census metropolitan areas and
                   agglomerations (from the 003CI file)

The source CSVs are 0.5-0.65 GB each, so they are streamed in chunks straight from the zips.
"""
import zipfile

import numpy as np
import pandas as pd

from .config import CMA_CI_ZIP, DATA_DIR, FSA_CI_ZIP, FSA_ZIP, PROVINCE_BY_LETTER

# CHARACTERISTIC_ID -> column, for 98-401-X2021013 (every FSA shares the same 2,631 ids)
FIELDS = {
    1: "pop_2021", 2: "pop_2016", 3: "pop_change_pct", 4: "dwellings_total", 5: "dwellings_occupied",
    # ids 6-7 (density, land area) are blank for every FSA in this release; build() takes them
    # from the FSA boundary file when it is present
    8: "age_total", 9: "age_0_14", 13: "age_15_64", 24: "age_65_plus", 28: "age_80_84", 29: "age_85_plus",
    40: "median_age",
    41: "dw_type_total", 42: "dw_single", 43: "dw_semi", 44: "dw_row", 45: "dw_duplex",
    46: "dw_apt_lt5", 47: "dw_apt_5plus", 48: "dw_other_attached", 49: "dw_movable",
    50: "hh_total", 51: "hh_1person", 57: "avg_hh_size",
    243: "median_hh_income", 345: "low_income_pct",
    1414: "tenure_total", 1416: "renters", 1418: "condo_total", 1419: "condo",
    1440: "built_total", 1441: "built_pre1961", 1442: "built_1961_1980", 1443: "built_1981_1990",
    1444: "built_1991_2000", 1445: "built_2001_2005", 1446: "built_2006_2010", 1447: "built_2011_2015",
    1448: "built_2016_2021",
    1456: "maint_total", 1462: "maint_65_74", 1463: "maint_75_84", 1464: "maint_85_plus",
    1488: "median_dwelling_value",
    1998: "edu_total", 2008: "edu_bachelor_plus",
    2223: "pop15_total", 2224: "labour_force", 2225: "employed", 2230: "unemployment_rate",
    2245: "self_employed",
    2261: "ind_total", 2266: "ind_manufacturing", 2267: "ind_wholesale", 2268: "ind_retail",
    2269: "ind_transport", 2273: "ind_professional",
    2593: "pow_total", 2594: "worked_at_home", 2596: "no_fixed_workplace",
    2603: "commute_total", 2607: "commute_transit",
}
# Household income is 100% data (no CI); the CI files carry 25% sample measures such as this one
CI_NAME = "Median employment income in 2020 for full-year full-time workers in 2020 ($)"
CHUNK = 400_000


def _data_member(zf):
    return max((i for i in zf.infolist() if i.filename.endswith("_CSV_data.csv")), key=lambda i: i.file_size)


def _stream(zpath, usecols, keep):
    """Yield filtered chunks of a census data CSV inside a zip."""
    zf = zipfile.ZipFile(zpath)
    with zf.open(_data_member(zf)) as fh:
        for chunk in pd.read_csv(fh, encoding="latin-1", usecols=usecols, dtype=str, chunksize=CHUNK):
            sub = keep(chunk)
            if len(sub):
                yield sub


def load_fsa_profile():
    ids = {str(k) for k in FIELDS}
    cols = ["ALT_GEO_CODE", "GEO_LEVEL", "TNR_SF", "TNR_LF", "CHARACTERISTIC_ID", "C1_COUNT_TOTAL"]
    long = pd.concat(_stream(FSA_ZIP, cols, lambda c: c[c.CHARACTERISTIC_ID.isin(ids)]))
    long = long[long.GEO_LEVEL == "Forward sortation area"]
    wide = (long.assign(field=long.CHARACTERISTIC_ID.astype(int).map(FIELDS),
                        value=pd.to_numeric(long.C1_COUNT_TOTAL, errors="coerce"))
            .pivot_table(index="ALT_GEO_CODE", columns="field", values="value", aggfunc="first"))
    quality = long.groupby("ALT_GEO_CODE")[["TNR_SF", "TNR_LF"]].first().apply(pd.to_numeric, errors="coerce")
    df = wide.join(quality.rename(columns={"TNR_SF": "nonresponse_short_pct", "TNR_LF": "nonresponse_long_pct"}))
    df.index.name = "fsa"
    return df.reset_index()


def load_fsa_income_ci():
    cols = ["ALT_GEO_CODE", "CHARACTERISTIC_NAME", "C1_COUNT_TOTAL", "C4_COUNT_LOW_CI_TOTAL", "C7_COUNT_HI_CI_TOTAL"]
    rows = pd.concat(_stream(FSA_CI_ZIP, cols, lambda c: c[c.CHARACTERISTIC_NAME.str.strip() == CI_NAME]))
    rows = rows.drop_duplicates("ALT_GEO_CODE")
    out = pd.DataFrame({"fsa": rows.ALT_GEO_CODE, "ft_employment_income": pd.to_numeric(rows.C1_COUNT_TOTAL, errors="coerce"),
                        "ft_income_ci_low": pd.to_numeric(rows.C4_COUNT_LOW_CI_TOTAL, errors="coerce"),
                        "ft_income_ci_high": pd.to_numeric(rows.C7_COUNT_HI_CI_TOTAL, errors="coerce")})
    return out


def load_cma_context():
    cols = ["ALT_GEO_CODE", "GEO_LEVEL", "GEO_NAME", "CHARACTERISTIC_NAME", "C1_COUNT_TOTAL",
            "C4_COUNT_LOW_CI_TOTAL", "C7_COUNT_HI_CI_TOTAL"]
    levels = {"Census metropolitan area", "Tracted census agglomeration", "Census agglomeration"}
    keep = lambda c: c[c.GEO_LEVEL.isin(levels) & (c.CHARACTERISTIC_NAME.str.strip() == CI_NAME)]
    rows = pd.concat(_stream(CMA_CI_ZIP, cols, keep)).drop_duplicates("ALT_GEO_CODE")
    num = lambda s: pd.to_numeric(s, errors="coerce")
    return pd.DataFrame({"code": rows.ALT_GEO_CODE, "level": rows.GEO_LEVEL, "name": rows.GEO_NAME,
                         "median_ft_employment_income": num(rows.C1_COUNT_TOTAL),
                         "ci_low": num(rows.C4_COUNT_LOW_CI_TOTAL), "ci_high": num(rows.C7_COUNT_HI_CI_TOTAL)})


def add_derived(df):
    """Shares and flags used by every model."""
    d = df.copy()
    d["province"] = d.fsa.str[0].map(PROVINCE_BY_LETTER)
    d["rural"] = d.fsa.str[1] == "0"          # Canada Post convention: a 0 in position 2 is a rural FSA
    d["vacant_dwellings"] = (d.dwellings_total - d.dwellings_occupied).clip(lower=0)
    ground = d[["dw_single", "dw_semi", "dw_row", "dw_duplex", "dw_other_attached", "dw_movable"]].sum(axis=1)
    apt = d[["dw_apt_lt5", "dw_apt_5plus"]].sum(axis=1)
    tot = (ground + apt).replace(0, np.nan)
    d["share_ground"] = ground / tot
    d["share_apartment"] = apt / tot
    bt = d.built_total.replace(0, np.nan)
    d["share_pre1981"] = (d.built_pre1961 + d.built_1961_1980) / bt
    d["share_1981_1990"] = d.built_1981_1990 / bt
    d["share_post1990"] = d[["built_1991_2000", "built_2001_2005", "built_2006_2010",
                             "built_2011_2015", "built_2016_2021"]].sum(axis=1) / bt
    d["share_65_plus"] = d.age_65_plus / d.age_total.replace(0, np.nan)
    d["share_renters"] = d.renters / d.tenure_total.replace(0, np.nan)
    d["share_work_home"] = d.worked_at_home / d.pow_total.replace(0, np.nan)
    d["share_bachelor"] = d.edu_bachelor_plus / d.edu_total.replace(0, np.nan)
    d["share_self_employed"] = d.self_employed / d.labour_force.replace(0, np.nan)
    d["share_transit"] = d.commute_transit / d.commute_total.replace(0, np.nan)
    d["income_ci_rel_width"] = (d.ft_income_ci_high - d.ft_income_ci_low) / d.ft_employment_income
    d["data_reliable"] = (d.pop_2021 >= 1000) & (d.income_ci_rel_width.fillna(1) < 0.25)
    return d


def build(force=False):
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "fsa_profile.csv"
    if out.exists() and not force:
        return pd.read_csv(out)
    print("  reading FSA census profile (645 MB)...")
    prof = load_fsa_profile()
    print("  reading FSA confidence intervals (624 MB)...")
    prof = prof.merge(load_fsa_income_ci(), on="fsa", how="left")
    from .addresses import boundary_file, fsa_areas
    if boundary_file():
        print("  adding land area from the FSA boundary file...")
        prof = prof.merge(fsa_areas(), on="fsa", how="left")
        prof["density_km2"] = prof.pop_2021 / prof.land_area_km2
        prof["dwellings_per_km2"] = prof.dwellings_total / prof.land_area_km2
    prof = add_derived(prof)
    prof.to_csv(out, index=False)
    print("  reading CMA/CA context with confidence intervals (487 MB)...")
    load_cma_context().to_csv(DATA_DIR / "cma_context.csv", index=False)
    return prof


if __name__ == "__main__":
    p = build(force=True)
    print(p.shape)
