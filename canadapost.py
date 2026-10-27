"""Canada Post commercial data products (release effective 2017-07-17).

* Householder Data (house.txt): Total Points of Call (houses, apartments, businesses, farms)
  for every delivery mode (LC letter carrier, SS suburban service, RR rural route, LB lock box,
  GD general delivery, ...) of every delivery installation, by FSA; record types 1/3 give
  each installation's street address. Layout: Householder Data Technical Specifications.
* Delivery Mode Data (dmode.txt): delivery mode type and route detail for every postal code.
  Layout: Delivery Mode Data Technical Specifications (July 2017).
* Postal Code Address Data (canada.add): civic number ranges by street, with postal code and
  delivery installation. No public layout; positions were derived from the records:
  type 1/2 records: municipality 4-34, street name 34-64, type 64-70, direction 70-72,
  parity 72 (1 odd, 2 even, 3 all), high number 73-79, low number 99-105, postal code
  167-173, installation postal code 173-179 (0-based).

Door-to-door conversions were frozen from 2015 to 2025, so 2017 delivery modes are close to
the network that the 2026-2030 conversion program starts from.
"""
import zipfile

import numpy as np
import pandas as pd

from .config import DATA_DIR, ROOT

CP_DIR = DATA_DIR / "canadapost"
HH_ZIP = ROOT / "hh-householder-data-samples.zip"
DMD_ZIP = ROOT / "dmd-delivery-mode-data-samples.zip"
PCAD_ZIP = ROOT / "pcad-postal-code-address-data-samples.zip"
COUNTS = ["apt", "bus", "farm", "house"]


def available():
    return HH_ZIP.exists() and DMD_ZIP.exists() and PCAD_ZIP.exists()


def norm(s):
    """Upper case, no accents or punctuation, single spaces (for street matching)."""
    s = pd.Series(s, dtype="object").fillna("").astype(str).str.upper()
    s = s.str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii")
    return s.str.replace(r"[^A-Z0-9 ]", " ", regex=True).str.split().str.join(" ")


def _lines(zpath, member):
    with zipfile.ZipFile(zpath).open(member) as fh:
        for raw in fh:
            yield raw.decode("latin-1").rstrip("\r\n")


# ------------------------------------------------------------------------- householder
def householder():
    """Delivery-mode count records and installation address records."""
    modes, inst = [], []
    num = lambda s, a, n: int(s[a - 1:a - 1 + n].strip() or 0)
    for s in _lines(HH_ZIP, "house.txt"):
        s = s.ljust(176)
        rt = s[82]
        if rt in "24":
            pc = s[104:110]
            modes.append({"prov": s[0:2], "rural": rt == "4", "mode": s[83:85], "mode_id": s[85:89].strip(),
                          "inst_name": f"{s[32:62].strip()} {s[62:67].strip()} {s[67:82].strip()}".strip(),
                          "inst_pc": pc, "fsa": s[110:113].strip() or pc[:3],
                          "apt": num(s, 144, 7), "bus": num(s, 151, 7), "farm": num(s, 158, 7),
                          "house": num(s, 165, 7), "high_demand": s[171:173] == "HD"})
        elif rt in "13":
            inst.append({"inst_pc": s[104:110], "prov": s[0:2],
                         "inst_name": f"{s[32:62].strip()} {s[62:67].strip()} {s[67:82].strip()}".strip(),
                         "number": s[110:116].strip(), "street_name": s[117:147].strip(),
                         "street_type": s[147:153].strip(), "street_dir": s[153:155].strip()})
    return pd.DataFrame(modes), pd.DataFrame(inst).drop_duplicates("inst_pc")


def fsa_counts(modes):
    """Points of call per FSA by delivery mode, plus route counts and the main depot."""
    m = modes.copy()
    m["res"] = m.house + m.apt
    out = pd.DataFrame(index=pd.Index(sorted(m.fsa.unique()), name="fsa"))
    lc = m[m["mode"] == "LC"].groupby("fsa")
    out["cp_lc_house"], out["cp_lc_apt"], out["cp_lc_bus"] = lc.house.sum(), lc.apt.sum(), lc.bus.sum()
    for code in ("SS", "RR", "LB"):
        out[f"cp_{code.lower()}_res"] = m[m["mode"] == code].groupby("fsa").res.sum()
    out["cp_other_res"] = m[~m["mode"].isin(["LC", "SS", "RR", "LB"])].groupby("fsa").res.sum()
    out["cp_business"] = m.groupby("fsa").bus.sum()
    out["cp_farm"] = m.groupby("fsa").farm.sum()
    out["cp_points_total"] = m.groupby("fsa")[COUNTS].sum().sum(axis=1)
    for code in ("LC", "SS", "RR"):
        out[f"cp_{code.lower()}_routes"] = m[m["mode"] == code].groupby("fsa").apply(
            lambda g: g[["inst_pc", "mode_id"]].drop_duplicates().shape[0])
    main = (m[m["mode"].isin(["LC", "SS"])].assign(pts=lambda x: x[COUNTS].sum(axis=1))
            .groupby(["fsa", "inst_pc", "inst_name"]).pts.sum().reset_index()
            .sort_values("pts", ascending=False).drop_duplicates("fsa").set_index("fsa"))
    out["cp_depot_pc"], out["cp_depot_name"] = main.inst_pc, main.inst_name
    num = [c for c in out.columns if c.startswith("cp_") and c not in ("cp_depot_pc", "cp_depot_name")]
    out[num] = out[num].fillna(0)
    return out.reset_index()


# ------------------------------------------------------------------------- delivery mode
def delivery_modes():
    rows = []
    for s in _lines(DMD_ZIP, "dmode.txt"):
        s = s.ljust(72)
        if s[0] == "2":
            rows.append((s[2:8], s[64], s[65:69].strip(), f"{s[8:36].strip()} {s[36:64].strip()}".strip()))
        elif s[0] == "1":
            rows.append((s[2:8], "R", "", s[36:64].strip()))
    return pd.DataFrame(rows, columns=["postal_code", "mode_type", "detail", "facility"])


# ---------------------------------------------------------------------- address ranges
def address_ranges():
    rows = []
    for s in _lines(PCAD_ZIP, "canada.add"):
        if s[:1] not in ("1", "2") or len(s) < 179:
            continue
        a, b = s[73:79], s[99:105]
        if not (a.isdigit() and b.isdigit()):
            continue
        a, b = int(a), int(b)
        rows.append((s[34:64].strip(), s[64:70].strip(), s[70:72].strip(), s[72], min(a, b), max(a, b),
                     s[167:173], s[173:179]))
    return pd.DataFrame(rows, columns=["name", "type", "dir", "parity", "lo", "hi", "postal_code", "inst_pc"])


def build(force=False):
    """Parse the three products once into data/canadapost/."""
    CP_DIR.mkdir(parents=True, exist_ok=True)
    files = {k: CP_DIR / f for k, f in (("modes", "householder_modes.csv"), ("inst", "installations.csv"),
                                         ("fsa", "fsa_counts.csv"), ("dmode", "delivery_modes.csv.gz"),
                                         ("ranges", "address_ranges.csv.gz"))}
    if force or not all(p.exists() for p in files.values()):
        print("  parsing Canada Post Householder, Delivery Mode and Postal Code Address data...")
        modes, inst = householder()
        modes.to_csv(files["modes"], index=False)
        inst.to_csv(files["inst"], index=False)
        fsa_counts(modes).to_csv(files["fsa"], index=False)
        delivery_modes().to_csv(files["dmode"], index=False, compression="gzip")
        address_ranges().to_csv(files["ranges"], index=False, compression="gzip")
    rd = lambda k: pd.read_csv(files[k], dtype=str if k in ("dmode", "ranges", "inst") else None,
                               keep_default_na=False if k in ("dmode",) else True)
    return {k: rd(k) for k in files}


# ---------------------------------------------------------- address -> postal code -> route
# Municipal short forms in ODA -> Canada Post street type codes
TYPE_ALIAS = {"AV": "AVE", "CR": "CRES", "WY": "WAY", "CO": "CRT", "CT": "CRT", "BV": "BLVD", "BL": "BLVD",
              "CI": "CIR", "CL": "CLOSE", "CV": "COVE", "GA": "GATE", "GT": "GATE", "GD": "GDNS", "GR": "GREEN",
              "GV": "GROVE", "HT": "HTS", "HL": "HILL", "LI": "LINK", "LN": "LANE", "ME": "MEWS", "MR": "MANOR",
              "MA": "MANOR", "PA": "PK", "PY": "PKY", "PKWY": "PKY", "RI": "RISE", "TC": "TERR", "TE": "TERR",
              "TR": "TRAIL", "VW": "VIEW", "VI": "VILLAS", "WK": "WALK", "HY": "HWY", "BA": "BAY", "LD": "LANDNG",
              "PZ": "PLAZA", "CM": "COMMON", "GL": "GLEN", "LP": "LOOP", "PH": "PATH", "HE": "HEATH",
              "SQUARE": "SQ", "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "COURT": "CRT",
              "CRESCENT": "CRES", "PLACE": "PL", "BOULEVARD": "BLVD", "LANE": "LANE", "TERRACE": "TERR"}


def _type(s):
    t = norm(s)
    return t.map(lambda v: TYPE_ALIAS.get(v, v))


def _num(s):
    return pd.to_numeric(pd.Series(s, dtype="object").astype(str).str.extract(r"^\s*(\d+)")[0], errors="coerce")


def assign_postal(locs, cp):
    """Give each ODA location its postal code, delivery mode type and letter carrier route.

    Match within the FSA on standardized street name + type + direction, then on the civic
    number falling inside a Canada Post number range of the same parity. Addresses still
    unmatched get a second pass on name + direction only (street type spelled differently).
    """
    r = cp["ranges"].copy()
    r["lo"], r["hi"] = r.lo.astype(int), r.hi.astype(int)
    base = r.postal_code.str[:3] + "|" + norm(r.name).values
    r["key"] = base + "|" + _type(r.type).values + "|" + norm(r.dir).values
    r["key2"] = base + "|" + norm(r.dir).values
    r = pd.concat([r[r.parity != "2"].assign(par=1), r[r.parity != "1"].assign(par=0)])
    r = r[["key", "key2", "par", "lo", "hi", "postal_code", "inst_pc"]].sort_values("lo")

    out = locs.drop(columns=[c for c in ("postal_code", "inst_pc", "mode_type", "route") if c in locs])
    lbase = out.fsa.fillna("") + "|" + norm(out.str_name).values
    left = pd.DataFrame({"i": np.arange(len(out)), "num": _num(out.street_no).values,
                         "key": (lbase + "|" + _type(out.str_type).values + "|" + norm(out.str_dir).values).values,
                         "key2": (lbase + "|" + norm(out.str_dir).values).values})
    left = left.dropna(subset=["num"])
    left["num"] = left.num.astype(int)
    left["par"] = left.num % 2
    hits = []
    for key in ("key", "key2"):
        todo = left[~left.i.isin(hits[0].i)] if hits else left
        m = pd.merge_asof(todo.sort_values("num"), r.drop(columns=["key2" if key == "key" else "key"]).sort_values("lo"),
                          left_on="num", right_on="lo", by=[key, "par"], direction="backward")
        hits.append(m[m.num <= m.hi][["i", "postal_code", "inst_pc"]])
    m = pd.concat(hits)
    for c in ("postal_code", "inst_pc"):
        out[c] = pd.Series(m[c].values, index=m.i.values).reindex(np.arange(len(out))).values
    dm = cp["dmode"].drop_duplicates("postal_code").set_index("postal_code")
    out["mode_type"] = dm.mode_type.reindex(out.postal_code).values
    detail = dm.detail.reindex(out.postal_code).fillna("").values
    out["route"] = np.where(out.postal_code.notna(), out.inst_pc.fillna("") + ":" + out.mode_type.fillna("") + detail, None)
    return out


def attach_by_postal(locs, cp):
    """Delivery mode, installation and route for addresses that already carry a postal code (NAR).

    Mode codes: Delivery Mode Data types (A block face, B apartment, E business building,
    H rural route, K PO box, T suburban service, R rural postal code, ...), overridden by the
    address's own delivery information (RR -> H, SS -> T, PO BOX -> K). Postal codes created
    after the 2017 release get "N" (new development since 2017; those get CMBs).
    """
    out = locs.copy()
    dm = cp["dmode"].drop_duplicates("postal_code").set_index("postal_code")
    pc = out.postal_code
    mode = dm.mode_type.reindex(pc).values
    detail = dm.detail.reindex(pc).fillna("").values
    info = out.delivery_info.fillna("").str.upper().str.strip() if "delivery_info" in out else pd.Series("", index=out.index)
    mode = np.where(info.str.match(r"^(RR|R R)\b"), "H", mode)
    mode = np.where(info.str.match(r"^(SS|S S)\b"), "T", mode)
    mode = np.where(info.str.contains(r"\bBOX\b"), "K", mode)
    mode = np.where(pd.isna(mode) & pc.notna().values, "N", mode)
    if "inst_by_pc" not in cp:
        cp["inst_by_pc"] = cp["ranges"].drop_duplicates("postal_code").set_index("postal_code").inst_pc
    inst = cp["inst_by_pc"]
    out["mode_type"] = mode
    out["inst_pc"] = inst.reindex(pc).values
    out["route"] = np.where(pd.notna(out.inst_pc) & ~pd.Series(mode).isin(["N"]).values,
                            out.inst_pc.fillna("") + ":" + pd.Series(mode).fillna("").values + detail, None)
    return out


def geocode_installations(inst, locs):
    """Depot coordinates: match each installation's street address to an ODA location."""
    key = lambda fsa, n, t, d: fsa + "|" + norm(n).values + "|" + _type(t).values + "|" + norm(d).values
    a = inst.assign(num=_num(inst.number).values,
                    key=key(inst.inst_pc.str[:3], inst.street_name, inst.street_type, inst.street_dir))
    b = locs.assign(num=_num(locs.street_no).values,
                    key=key(locs.fsa.fillna(""), locs.str_name, locs.str_type, locs.str_dir))
    b = b.dropna(subset=["num"]).drop_duplicates(["key", "num"])[["key", "num", "lat", "lon"]]
    g = a.merge(b, on=["key", "num"], how="left")
    g["geocode"] = np.where(g.lat.notna(), "address match", None)
    served = locs.dropna(subset=["inst_pc"]).groupby("inst_pc")[["lat", "lon"]].mean()

    # second pass: depot address outside its own FSA, or street type spelled differently.
    # Take the same street name + direction + number nearest the area the depot serves (<= 25 km).
    miss = g.lat.isna()
    if miss.any():
        k2 = lambda n, d: norm(n).values + "|" + norm(d).values
        cand = locs.assign(num=_num(locs.street_no).values, k=k2(locs.str_name, locs.str_dir)).dropna(subset=["num"])
        want = g[miss].assign(k=k2(g[miss].street_name, g[miss].street_dir))
        j = want.reset_index().merge(cand[["k", "num", "lat", "lon"]], on=["k", "num"], suffixes=("", "_c"))
        j = j.join(served, on="inst_pc", rsuffix="_s").dropna(subset=["lat_s"])
        j["km"] = np.hypot((j.lat_c - j.lat_s) * 111, (j.lon_c - j.lon_s) * 111 * np.cos(np.radians(j.lat_s)))
        best = j[j.km <= 25].sort_values("km").drop_duplicates("index").set_index("index")
        g.loc[best.index, "lat"], g.loc[best.index, "lon"] = best.lat_c, best.lon_c
        g.loc[best.index, "geocode"] = "address match (nearby)"

    # fallback: centroid of the addresses this installation serves
    miss = g.lat.isna()
    g.loc[miss, "lat"] = served.lat.reindex(g.inst_pc[miss]).values
    g.loc[miss, "lon"] = served.lon.reindex(g.inst_pc[miss]).values
    g.loc[miss & g.lat.notna(), "geocode"] = "centroid of served addresses"
    return g.drop(columns=["key", "num"])
