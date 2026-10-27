"""Statistics Canada Open Database of Addresses (ODA) -> delivery points.

Each ODA row is one civic address (one row per unit where units are recorded). Rows at the
same coordinates are one delivery location, so a location with 5+ units is treated as an
apartment lobby and the rest as ground-oriented homes.

FSA assignment, in order of preference:
1. point-in-polygon against the StatCan 2021 FSA Boundary File (any lfsa000*21* file in
   the project folder, shapefile or geodatabase, zipped or not);
2. the ODA postal_code field (well filled only for New Brunswick).

Outputs: data/oda/<PR>.csv.gz (delivery locations) and data/oda_coverage.csv (ODA addresses
vs census dwellings per census subdivision, showing where ODA is complete enough to use).
"""
import glob
import zipfile

import numpy as np
import pandas as pd

from .config import DATA_DIR, ROOT

ODA_DIR = DATA_DIR / "oda"
COLS = ["latitude", "longitude", "street_no", "str_name_pcs", "str_type_pcs", "str_dir_pcs", "unit",
        "postal_code", "csduid", "csdname", "pruid"]
PR_CODE = {"10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON", "46": "MB",
           "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU"}
LOBBY_MIN_UNITS = 5
DTYPES = {c: str for c in ("csduid", "pruid", "fsa", "fsa_postal", "street_no", "street", "str_name", "str_type",
                           "str_dir", "postal_code", "mode_type", "route", "inst_pc", "delivery_info", "csdname")}


def oda_zips():
    return sorted(p for p in map(__import__("pathlib").Path, glob.glob(str(ROOT / "*ODA_*_v1.zip"))))


def _read(zpath):
    zf = zipfile.ZipFile(zpath)
    member = next(n for n in zf.namelist() if n.startswith("ODA_") and n.endswith(".csv"))
    parts = []
    with zf.open(member) as fh:
        for ch in pd.read_csv(fh, usecols=COLS, dtype=str, chunksize=500_000,
                              encoding="utf-8", encoding_errors="replace"):
            parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    df["latitude"] = pd.to_numeric(df.latitude, errors="coerce")
    df["longitude"] = pd.to_numeric(df.longitude, errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    return df.drop_duplicates(["latitude", "longitude", "street_no", "str_name_pcs", "unit"])


def to_locations(df):
    """Collapse addresses to delivery locations (one per coordinate pair)."""
    df = df.assign(lat5=df.latitude.round(5), lon5=df.longitude.round(5),
                   street=(df.str_name_pcs.fillna("") + " " + df.str_type_pcs.fillna("")
                           + " " + df.str_dir_pcs.fillna("")).str.strip(),
                   fsa=df.postal_code.str.replace(" ", "").str[:3].str.upper())
    g = df.groupby(["lat5", "lon5"], sort=False)
    loc = g.agg(units=("street_no", "size"), street=("street", "first"), street_no=("street_no", "first"),
                str_name=("str_name_pcs", "first"), str_type=("str_type_pcs", "first"),
                str_dir=("str_dir_pcs", "first"),
                csduid=("csduid", "first"), csdname=("csdname", "first"), pruid=("pruid", "first"),
                fsa_postal=("fsa", "first")).reset_index().rename(columns={"lat5": "lat", "lon5": "lon"})
    loc["kind"] = np.where(loc.units >= LOBBY_MIN_UNITS, "lobby", "ground")
    return loc


def boundary_file():
    hits = [p for p in glob.glob(str(ROOT / "**" / "*lfsa000*21*"), recursive=True)
            if p.lower().endswith((".shp", ".gdb", ".zip"))]
    return hits[0] if hits else None


def read_boundaries(boundary=None):
    """FSA polygons (CFSAUID, geometry) from the boundary file, zipped or not."""
    import geopandas as gpd
    boundary = boundary or boundary_file()
    if boundary.lower().endswith(".zip"):
        shp = next(n for n in zipfile.ZipFile(boundary).namelist() if n.lower().endswith(".shp"))
        boundary = f"zip://{boundary}!{shp}"
    return gpd.read_file(boundary)


def fsa_areas(boundary=None):
    """Land area (km2) per FSA from the polygons (StatCan Lambert projection)."""
    fsa = read_boundaries(boundary)
    if "LANDAREA" in fsa.columns:
        area = pd.to_numeric(fsa.LANDAREA, errors="coerce")
    else:
        area = fsa.to_crs(3347).area / 1e6
    return pd.DataFrame({"fsa": fsa.CFSAUID, "land_area_km2": area.values})


def assign_fsa(loc, boundary):
    import geopandas as gpd
    fsa = read_boundaries(boundary)[["CFSAUID", "geometry"]]
    pts = gpd.GeoDataFrame(loc, geometry=gpd.points_from_xy(loc.lon, loc.lat), crs="EPSG:4326").to_crs(fsa.crs)
    j = gpd.sjoin(pts, fsa, how="left", predicate="within")
    return j.groupby(level=0).CFSAUID.first().reindex(loc.index)


def build(force=False):
    ODA_DIR.mkdir(parents=True, exist_ok=True)
    from . import canadapost
    boundary = boundary_file()
    cp = canadapost.build() if canadapost.available() else None
    cov = []
    for z in oda_zips():
        pr = z.stem.split("ODA_")[1][:2]
        out = ODA_DIR / f"{pr}.csv.gz"
        loc = pd.read_csv(out, dtype=DTYPES) if out.exists() and not force else None
        if loc is None or "str_name" not in loc:
            print(f"  {pr}: reading {z.name}")
            loc = to_locations(_read(z))
            loc["fsa"] = assign_fsa(loc, boundary) if boundary else loc.fsa_postal
            loc.to_csv(out, index=False, compression="gzip")
        if cp is not None and "route" not in loc:
            print(f"  {pr}: matching addresses to Canada Post postal codes and routes")
            loc = canadapost.assign_postal(loc, cp)
            loc.to_csv(out, index=False, compression="gzip")
        c = loc.groupby("csduid").agg(csdname=("csdname", "first"), locations=("units", "size"),
                                     addresses=("units", "sum")).reset_index()
        c["province"] = pr
        cov.append(c)
    cov = pd.concat(cov, ignore_index=True)
    census = pd.read_csv(ROOT / "census_trimmed_98-401-X2021003.csv", dtype=str)
    census = census[(census.GEO_LEVEL == "Census subdivision") &
                    (census.CHARACTERISTIC_NAME == "Total private dwellings")]
    census = census.assign(csduid=census.ALT_GEO_CODE, dwellings=pd.to_numeric(census.C1_COUNT_TOTAL))
    cov = cov.merge(census[["csduid", "dwellings"]], on="csduid", how="left")
    cov["coverage"] = cov.addresses / cov.dwellings
    cov.to_csv(DATA_DIR / "oda_coverage.csv", index=False)
    return cov, bool(boundary)


def rematch():
    """Re-run the Canada Post postal-code and route match on the cached delivery locations."""
    from . import canadapost
    cp = canadapost.build()
    for f in sorted(ODA_DIR.glob("*.csv.gz")):
        loc = canadapost.assign_postal(pd.read_csv(f, dtype=DTYPES), cp)
        loc.to_csv(f, index=False, compression="gzip")
        print(f"  {f.name[:2]}: {loc.postal_code.notna().mean():.0%} matched")


def load(provinces=None):
    files = sorted(ODA_DIR.glob("*.csv.gz"))
    return pd.concat([pd.read_csv(f, dtype=DTYPES) for f in files
                      if provinces is None or f.name[:2] in provinces], ignore_index=True)


if __name__ == "__main__":
    cov, has_boundary = build(force=True)
    print("FSA boundary file found:", has_boundary)
    print(cov.groupby("province")[["locations", "addresses"]].sum())
