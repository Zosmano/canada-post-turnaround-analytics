"""Statistics Canada National Address Register (NAR, table 46-26-0002, released June 26, 2026).

One NAR location is one building and one NAR address is one building unit, so a location's
address count is its number of delivery points. Each address carries its mailing postal code,
a building-use code (1 residential, 2 partly residential, 3 non-residential, 4 unknown) and
additional delivery information (e.g. "RR 1", "SS 6", "PO BOX 62").

Output per province: data/nar/<PR>.csv.gz, one row per building, in the same schema as the
ODA delivery locations (lat, lon, units, street fields, fsa, kind), plus EPSG:3347 x/y,
residential and non-residential unit counts, and the mailing postal code.
"""
import zipfile

import numpy as np
import pandas as pd

from .config import DATA_DIR, ROOT

NAR_ZIP = ROOT / "Road network file.zip"     # the download's name; it holds the NAR CSVs
NAR_DIR = DATA_DIR / "nar"
PROV = {"10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON", "46": "MB", "47": "SK",
        "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU"}
COLS = ["LOC_GUID", "CIVIC_NO", "MAIL_STREET_NAME", "MAIL_STREET_TYPE", "MAIL_STREET_DIR", "MAIL_POSTAL_CODE",
        "CSD_ENG_NAME", "BU_USE", "BU_N_CIVIC_ADD", "BG_X", "BG_Y"]
LOBBY_MIN_UNITS = 5


def available():
    return NAR_ZIP.exists()


def _members(zf, code):
    return sorted(n for n in zf.namelist() if n.startswith(f"Addresses/Address_{code}") and n.endswith(".csv"))


def _province(zf, code):
    parts = []
    for m in _members(zf, code):
        with zf.open(m) as fh:
            for ch in pd.read_csv(fh, usecols=COLS, dtype=str, chunksize=1_000_000, encoding="utf-8-sig"):
                parts.append(ch)
    a = pd.concat(parts, ignore_index=True)
    a["res"] = a.BU_USE.isin(["1", "2", "4"]).astype(int)
    a["nonres"] = (a.BU_USE == "3").astype(int)
    a["x"] = pd.to_numeric(a.BG_X, errors="coerce")
    a["y"] = pd.to_numeric(a.BG_Y, errors="coerce")
    g = a.dropna(subset=["x", "y"]).groupby("LOC_GUID", sort=False)
    loc = g.agg(x=("x", "first"), y=("y", "first"), units=("res", "size"), res_units=("res", "sum"),
                nonres_units=("nonres", "sum"), street_no=("CIVIC_NO", "first"),
                str_name=("MAIL_STREET_NAME", "first"), str_type=("MAIL_STREET_TYPE", "first"),
                str_dir=("MAIL_STREET_DIR", "first"), postal_code=("MAIL_POSTAL_CODE", "first"),
                csdname=("CSD_ENG_NAME", "first"), delivery_info=("BU_N_CIVIC_ADD", "first")).reset_index(drop=True)
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(3347, 4326, always_xy=True).transform(loc.x.values, loc.y.values)
    loc["lat"], loc["lon"] = np.round(lat, 6), np.round(lon, 6)
    loc["postal_code"] = loc.postal_code.str.replace(" ", "").str.upper()
    loc["fsa"] = loc.postal_code.str[:3]
    loc["street"] = (loc.str_name.fillna("") + " " + loc.str_type.fillna("") + " " + loc.str_dir.fillna("")).str.strip()
    loc["pruid"] = code
    loc["kind"] = np.where(loc.res_units == 0, "business",
                           np.where(loc.res_units >= LOBBY_MIN_UNITS, "lobby", "ground"))
    loc["x"], loc["y"] = loc.x.round(1), loc.y.round(1)
    return loc


def build(force=False):
    """Parse every province once into data/nar/ (about 10 minutes for 3.9 GB of CSV)."""
    NAR_DIR.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(NAR_ZIP)
    from . import canadapost
    cp = canadapost.build() if canadapost.available() else None
    for code, pr in PROV.items():
        out = NAR_DIR / f"{pr}.csv.gz"
        if out.exists() and not force:
            continue
        print(f"  {pr}: reading National Address Register")
        loc = _province(zf, code)
        if cp is not None:
            loc = canadapost.attach_by_postal(loc, cp)
        loc.to_csv(out, index=False, compression="gzip")


def summary():
    """Locations, delivery points and postal-code coverage per province."""
    rows = []
    for f in sorted(NAR_DIR.glob("*.csv.gz")):
        d = pd.read_csv(f, usecols=["units", "res_units", "nonres_units", "postal_code", "kind", "mode_type"], dtype=str)
        n = lambda c: pd.to_numeric(d[c]).sum()
        rows.append({"province": f.name[:2], "locations": len(d), "addresses": n("units"),
                     "residential_units": n("res_units"), "nonresidential_units": n("nonres_units"),
                     "postal_code_rate": d.postal_code.notna().mean(),
                     "cp_mode_rate": d.mode_type.notna().mean() if "mode_type" in d else 0.0})
    return pd.DataFrame(rows)
