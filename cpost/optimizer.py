"""Community-mailbox siting and delivery-route optimization.

Two geometries share one solver:
* real addresses: Open Database of Addresses (ODA) points for an FSA, calibrated to the
  FSA's census dwelling counts and split into carrier zones; distance = straight line x
  road circuity factor (swap in Road Network File distances when available);
* synthetic street grid: a neighbourhood whose dwelling mix matches the FSA census profile,
  used where no address data exists; distance = exact grid street-network distance.

Pipeline per area:
1. Site CMBs: capacitated facility location. Greedy maximum coverage gives a feasible open
   set, min-cost flow gives the optimal household-to-site assignment under capacity and
   walking-distance limits, then local search closes surplus sites and re-centres the rest.
2. Route: vehicle routing with a shift-duration limit. Clarke-Wright savings builds routes,
   2-opt improves each route, and inter-route relocation balances them.
3. Compare before (carriers walk door-to-door; lobbies and existing CMBs by vehicle) with
   after (every household at a CMB or lobby, all by vehicle) in hours, km and dollars.
"""
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd
import shapely

from . import config as C

BLOCK_X = 120.0       # cross street spacing (m)
STREET_GAP = 70.0     # spacing between parallel residential streets (m)
LOT_FRONTAGE = 15.0
STREET_LEN = 1200.0
HOUSE_OFFSET = 12.0
APT_OFFSET = 30.0
SITE_STEP = 40.0
DEPOT = (0.0, -600.0)
ZONE_HOUSEHOLDS = 1500


@dataclass
class Area:
    x: np.ndarray       # metres east (grid: position along the street)
    sy: np.ndarray      # metres north (grid: street centreline)
    off: np.ndarray     # driveway length from street (m); 0 for real points
    side: np.ndarray    # +1 / -1, side of the street (plotting only)
    kind: np.ndarray    # "door" | "cmb" | "lobby"
    units: np.ndarray   # households at the point (1 for houses, n for apartment buildings)
    streets: np.ndarray
    metric: str = "grid"

    def plot_y(self, idx=None):
        idx = slice(None) if idx is None else idx
        return self.sy[idx] + self.side[idx] * self.off[idx]

    def subset(self, idx):
        return Area(self.x[idx], self.sy[idx], self.off[idx], self.side[idx], self.kind[idx],
                    self.units[idx], self.streets, self.metric)


def network_distance(xa, ya, oa, xb, yb, ob):
    """Street-grid distance between point sets A (rows) and B (columns), in metres."""
    xa, ya, oa = (np.asarray(v, float)[:, None] for v in (xa, ya, oa))
    xb, yb, ob = (np.asarray(v, float)[None, :] for v in (xb, yb, ob))
    lo, hi = np.minimum(xa, xb), np.maximum(xa, xb)
    has_cross = np.floor(hi / BLOCK_X) * BLOCK_X >= lo - 1e-9
    detour = np.where(has_cross, 0.0,
                      np.minimum(lo - np.floor(lo / BLOCK_X) * BLOCK_X, np.ceil(hi / BLOCK_X) * BLOCK_X - hi))
    same = np.abs(ya - yb) < 1e-6
    return oa + ob + np.where(same, np.abs(xa - xb), np.abs(ya - yb) + np.abs(xa - xb) + 2 * detour)


def road_distance(xa, ya, oa, xb, yb, ob):
    """Real points: straight-line distance x circuity (typical urban detour index)."""
    xa, ya, oa = (np.asarray(v, float)[:, None] for v in (xa, ya, oa))
    xb, yb, ob = (np.asarray(v, float)[None, :] for v in (xb, yb, ob))
    return oa + ob + C.ROAD_CIRCUITY * np.hypot(xa - xb, ya - yb)


def distance(metric, *args):
    if isinstance(metric, str):
        return (network_distance if metric == "grid" else road_distance)(*args)
    return metric.distance(*args)          # RoadNetwork: shortest paths on real streets


# ------------------------------------------------------------------------------- areas
def _modelled_points(row):
    """Homes and apartments delivered at the address (excludes PO boxes and rural routes)."""
    return row["ground_points"] + row["apartment_points"]


def synth_area(row, n_points=900, seed=0):
    """Neighbourhood sample whose composition matches one FSA's census profile."""
    rng = np.random.default_rng(seed)
    n_ground = int(round(n_points * row["ground_points"] / _modelled_points(row)))
    n_apt = n_points - n_ground
    door_frac = row["door_points"] / max(row["ground_points"], 1)
    n_door = int(round(n_ground * door_frac))

    per_street = int(2 * STREET_LEN / LOT_FRONTAGE)
    n_streets = max(1, int(np.ceil(n_ground / per_street)))
    streets = np.arange(n_streets) * STREET_GAP
    lots = np.arange(per_street // 2) * LOT_FRONTAGE + LOT_FRONTAGE / 2
    hx, hy, hs = [], [], []
    for s in streets:                       # older streets first, so door-to-door homes cluster together
        for side in (-1, 1):
            hx.extend(lots); hy.extend([s] * len(lots)); hs.extend([side] * len(lots))
    hx, hy, hs = (np.array(v[:n_ground]) for v in (hx, hy, hs))
    kind = np.array(["door"] * n_door + ["cmb"] * (n_ground - n_door))

    # Apartment buildings sized by the FSA's split between low-rise and 5+ storey stock
    tall_share = row.get("dw_apt_5plus", 0) / max(row.get("dw_apt_5plus", 0) + row.get("dw_apt_lt5", 0), 1)
    bx, by, bs, bu = [], [], [], []
    left = n_apt
    while left > 0:
        u = int(min(left, rng.integers(60, 121) if rng.random() < tall_share else rng.integers(8, 25)))
        bx.append(rng.integers(0, int(STREET_LEN / BLOCK_X)) * BLOCK_X + BLOCK_X / 2)
        by.append(rng.choice(streets)); bs.append(rng.choice([-1, 1])); bu.append(u)
        left -= u
    jitter = rng.uniform(-2, 2, n_ground)
    return Area(
        x=np.concatenate([hx + jitter, np.array(bx, float)]),
        sy=np.concatenate([hy, np.array(by, float)]),
        off=np.concatenate([np.full(n_ground, HOUSE_OFFSET), np.full(len(bx), APT_OFFSET)]),
        side=np.concatenate([hs, np.array(bs)]),
        kind=np.concatenate([kind, np.array(["lobby"] * len(bx))]),
        units=np.concatenate([np.ones(n_ground, int), np.array(bu, int)]),
        streets=streets)


def _sample(rng, idx, target):
    return np.sort(rng.choice(idx, target, replace=False)) if len(idx) > target else idx


def real_area(row, locs, seed=0, depot_ll=None):
    """FSA from ODA delivery locations, calibrated to the FSA's delivery-point counts.

    Where an address matched a Canada Post postal code, its delivery mode type decides its role:
    A block face -> home on a letter-carrier route (door-to-door candidate); B apartment building
    -> lobby; T suburban service -> already centralized; E/G/M business and K/J/R/H/X PO box,
    rural and mobile -> not part of residential conversion. Unmatched addresses fall back to
    their unit count (5+ units = lobby).
    Counts come from the plan (Canada Post Householder data, census otherwise): door-eligible
    homes and suburban homes are sampled from matching ODA points; apartment units are spread
    over lobby points by recorded units. Door-to-door is assigned by whole letter-carrier route
    (by street where the route is unknown) until the FSA's modelled door share is met.
    Returns the area, the depot position, ODA coverage and the postal-code match rate.
    """
    rng = np.random.default_rng(seed)
    if "x" in locs and locs.x.notna().all():     # NAR: Statistics Canada Lambert (EPSG:3347) metres
        origin = (locs.x.mean(), locs.y.mean())
        x, y = locs.x.values - origin[0], locs.y.values - origin[1]

        def proj(lat, lon):
            from pyproj import Transformer
            px, py = Transformer.from_crs(4326, 3347, always_xy=True).transform(lon, lat)
            return px - origin[0], py - origin[1]
    else:                                         # ODA: local equirectangular projection
        origin = None
        lat0, lon0 = locs.lat.mean(), locs.lon.mean()
        proj = lambda lat, lon: ((lon - lon0) * 111_320 * np.cos(np.radians(lat0)), (lat - lat0) * 110_540)
        x, y = proj(locs.lat.values, locs.lon.values)
    mt = locs.mode_type.fillna("").values if "mode_type" in locs else np.full(len(locs), "")
    units = (locs.res_units if "res_units" in locs else locs.units).values.astype(int)
    home = (locs.kind.values != "business") & (units > 0)
    lobby_mask = home & ((mt == "B") | ((mt == "") & (units >= 5)) | ((mt == "A") & (units >= 5)))
    ground_mask = home & ((mt == "A") | (mt == "")) & ~lobby_mask
    # T suburban service, N new development since 2017: already on centralized delivery
    ss_mask = home & ((mt == "T") | (mt == "N")) & ~lobby_mask

    ss_target = int(round(row.get("cp_ss_res", 0) or 0)) + int((home & (mt == "N") & ~lobby_mask).sum())
    g_target = int(round(row["ground_points"])) - ss_target
    ground = np.where(ground_mask)[0]
    coverage = (ground_mask.sum() + ss_mask.sum()) / max(row["ground_points"], 1)
    ground = _sample(rng, ground, max(g_target, 0))
    ss = _sample(rng, np.where(ss_mask)[0], ss_target)
    lobby = np.where(lobby_mask)[0]
    a_target = int(round(row["apartment_points"]))
    if a_target and not len(lobby):          # no multi-unit points recorded: use spare ground points
        spare = np.setdiff1d(np.where(ground_mask)[0], ground)
        pool = spare if len(spare) else ground
        lobby = rng.choice(pool, max(1, a_target // 16), replace=False)
        ground = np.setdiff1d(ground, lobby)
    w = units[lobby].astype(float)
    units_lobby = np.maximum(1, np.round(a_target * w / w.sum())).astype(int) if len(lobby) else np.array([], int)

    route = locs.route.values if "route" in locs else np.full(len(locs), None)
    groups = np.array([r if isinstance(r, str) and r else "st:" + str(s)
                       for r, s in zip(route[ground], locs.street.fillna("").values[ground])])
    names, counts = np.unique(groups, return_counts=True)
    order = rng.permutation(len(names))
    door_target = row["door_points"] / max(row["door_candidates"], 1) * len(ground)
    chosen, n = [], 0
    for i in order:
        if n >= door_target:
            break
        chosen.append(names[i]); n += counts[i]
    kind_ground = np.where(np.isin(groups, chosen), "door", "cmb")

    idx = np.concatenate([ground, ss, lobby])
    area = Area(x=x[idx], sy=y[idx], off=np.zeros(len(idx)), side=np.zeros(len(idx)),
                kind=np.concatenate([kind_ground, np.full(len(ss), "cmb"), np.full(len(lobby), "lobby")]),
                units=np.concatenate([np.ones(len(ground) + len(ss), int), units_lobby]),
                streets=np.array([]), metric="road")
    depot = tuple(map(float, proj(*depot_ll))) if depot_ll is not None and np.all(np.isfinite(depot_ll)) else (0.0, 0.0)
    matched = float(pd.notna(locs.mode_type).mean()) if "mode_type" in locs else 0.0
    return area, depot, coverage, matched, origin


def zones(area, target=ZONE_HOUSEHOLDS, seed=0):
    """Split an area into carrier zones of about `target` households (weighted k-means)."""
    from sklearn.cluster import KMeans
    k = max(1, int(np.ceil(area.units.sum() / target)))
    if k == 1:
        return [np.arange(len(area.x))]
    lab = KMeans(k, n_init=4, random_state=seed).fit(np.c_[area.x, area.sy], sample_weight=area.units).labels_
    return [np.where(lab == z)[0] for z in range(k)]


# ---------------------------------------------------------------------------- CMB siting
def _candidates(area, households):
    if area.metric == "grid":
        xs = np.arange(0, STREET_LEN + 1e-9, SITE_STEP)
        return np.tile(xs, len(area.streets)), np.repeat(area.streets, len(xs)), np.full(len(xs) * len(area.streets), 3.0)
    # real points: one candidate per 40 m cell, placed at the household nearest the cell centre
    hx, hy = area.x[households], area.sy[households]
    cell = np.floor(hx / SITE_STEP).astype(int) * 100_000 + np.floor(hy / SITE_STEP).astype(int)
    cx, cy = [], []
    for c in np.unique(cell):
        m = np.where(cell == c)[0]
        k = m[np.argmin(np.hypot(hx[m] - hx[m].mean(), hy[m] - hy[m].mean()))]
        cx.append(hx[k]); cy.append(hy[k])
    return np.array(cx), np.array(cy), np.zeros(len(cx))


def _assign(D, open_sites, cap, max_walk):
    """Optimal capacitated assignment via min-cost flow. Returns site per household or None."""
    n = D.shape[0]
    G = nx.DiGraph()
    G.add_node("s", demand=-n)
    G.add_node("t", demand=n)
    for h in range(n):
        G.add_edge("s", ("h", h), capacity=1, weight=0)
        for c in open_sites:
            if D[h, c] <= max_walk:
                G.add_edge(("h", h), ("c", c), capacity=1, weight=int(D[h, c]))
    for c in open_sites:
        G.add_edge(("c", c), "t", capacity=cap, weight=0)
    try:
        flow = nx.min_cost_flow(G)
    except nx.NetworkXUnfeasible:
        return None
    out = np.full(n, -1)
    for h in range(n):
        for (_, c), f in flow[("h", h)].items():
            if f:
                out[h] = c
    return out


def site_cmbs(area, households, cap=C.CMB_SITE_CAPACITY, max_walk=C.CMB_MAX_WALK_M):
    """Capacitated facility location for the given household indices."""
    cx, cy, co = _candidates(area, households)
    D = distance(area.metric, area.x[households], area.sy[households], area.off[households], cx, cy, co)
    cover = D <= max_walk
    uncovered = np.ones(len(households), bool)
    opened = []
    while uncovered.any():                                   # greedy max coverage, capacity-capped
        gain = np.minimum((cover & uncovered[:, None]).sum(0), cap)
        c = int(gain.argmax())
        if gain[c] == 0:
            raise ValueError("some households have no candidate CMB site within the walking limit")
        opened.append(c)
        near = np.where(cover[:, c] & uncovered)[0]
        uncovered[near[np.argsort(D[near, c])][:cap]] = False
    assign = _assign(D, opened, cap, max_walk)
    while assign is None:                                    # greedy capacity was optimistic: add a site
        opened.append(int(np.where(np.isin(np.arange(D.shape[1]), opened), -1, cover.sum(0)).argmax()))
        assign = _assign(D, opened, cap, max_walk)

    for site in sorted(opened, key=lambda c: (assign == c).sum()):   # close surplus sites
        trial = [c for c in opened if c != site]
        a = _assign(D, trial, cap, max_walk)
        if a is not None:
            opened, assign = trial, a

    for _ in range(2):                                       # re-centre each site on its households
        moved = []
        for c in opened:
            members = np.where(assign == c)[0]
            ok = cover[members].all(0)
            ok[[o for o in opened if o != c]] = False
            moved.append(int(np.where(ok, D[members].sum(0), np.inf).argmin()) if ok.any() else c)
        a = _assign(D, moved, cap, max_walk)
        if a is not None:
            opened, assign = moved, a
    sites = np.array(opened)
    walk = D[np.arange(len(households)), assign]
    return {"x": cx[sites], "y": cy[sites], "off": co[sites],
            "load": np.array([(assign == c).sum() for c in sites]),
            "walk_sum_m": float(walk.sum()), "max_walk_m": float(walk.max()), "n": len(households)}


# -------------------------------------------------------------------------------- routing
def _route_time(r, T, svc):
    seq = [0] + r + [0]
    return float(T[seq[:-1], seq[1:]].sum() + svc[r].sum())


def clarke_wright(T, svc, max_t):
    n = T.shape[0] - 1
    routes = {i: [i] for i in range(1, n + 1)}
    where = list(range(n + 1))
    rtime = {i: T[0, i] + svc[i] + T[i, 0] for i in range(1, n + 1)}
    iu, ju = np.triu_indices(n, 1)
    iu, ju = iu + 1, ju + 1
    s = T[0, iu] + T[0, ju] - T[iu, ju]
    keep = s > 0
    order = np.argsort(-s[keep], kind="stable")
    for i, j, sv in zip(iu[keep][order], ju[keep][order], s[keep][order]):
        ri, rj = where[i], where[j]
        if ri == rj:
            continue
        A, B = routes[ri], routes[rj]
        if A[-1] != i:
            if A[0] != i:
                continue
            A = A[::-1]
        if B[0] != j:
            if B[-1] != j:
                continue
            B = B[::-1]
        t = rtime[ri] + rtime[rj] - sv
        if t > max_t:
            continue
        routes[ri] = A + B
        rtime[ri] = t
        del routes[rj], rtime[rj]
        for k in B:
            where[k] = ri
    return list(routes.values())


def two_opt(r, T, max_pass=60):
    seq = np.array([0] + r + [0])
    for _ in range(max_pass):
        improved = False
        for i in range(1, len(seq) - 2):
            a, b = seq[i - 1], seq[i]
            c, d = seq[i + 1:-1], seq[i + 2:]
            delta = T[a, c] + T[b, d] - T[a, b] - T[c, d]
            k = int(delta.argmin())
            if delta[k] < -1e-6:
                j = i + 1 + k
                seq[i:j + 1] = seq[i:j + 1][::-1]
                improved = True
        if not improved:
            break
    return list(seq[1:-1])


def relocate(routes, T, svc, max_t, max_pass=4):
    times = [_route_time(r, T, svc) for r in routes]
    for _ in range(max_pass):
        moved = 0
        for ri in range(len(routes)):
            p = 0
            while p < len(routes[ri]):
                r = routes[ri]
                v = r[p]
                prev = r[p - 1] if p > 0 else 0
                nxt = r[p + 1] if p + 1 < len(r) else 0
                gain = T[prev, v] + T[v, nxt] - T[prev, nxt]
                best = None
                for rj in range(len(routes)):
                    if rj == ri:
                        continue
                    seq = np.array([0] + routes[rj] + [0])
                    ins = T[seq[:-1], v] + T[v, seq[1:]] - T[seq[:-1], seq[1:]]
                    k = int(ins.argmin())
                    if ins[k] < gain - 1e-6 and times[rj] + ins[k] + svc[v] <= max_t:
                        if best is None or ins[k] < best[2]:
                            best = (rj, k, ins[k])
                if best:
                    rj, k, cost = best
                    routes[rj].insert(k, v)
                    del routes[ri][p]
                    times[rj] += cost + svc[v]
                    times[ri] -= gain + svc[v]
                    moved += 1
                else:
                    p += 1
        if not moved:
            break
    return [r for r in routes if r]


def solve_routes(xs, ys, offs, svc, mode, metric="grid", depot=DEPOT):
    """VRP over stops (depot prepended). Returns routes, hours and km."""
    if len(xs) == 0:
        return {"routes": [], "hours": 0.0, "vehicle_km": 0.0, "n_routes": 0}
    dx = np.concatenate([[depot[0]], xs]); dy = np.concatenate([[depot[1]], ys])
    do = np.concatenate([[0.0], offs])
    D = distance(metric, dx, dy, do, dx, dy, do)
    speed = (C.WALK_SPEED_KMH if mode == "walk" else C.DRIVE_SPEED_KMH) / 3.6
    T = D / speed
    drive = C.DRIVE_SPEED_KMH / 3.6
    T[0, :] = D[0, :] / drive          # carriers are driven to and from their walk
    T[:, 0] = D[:, 0] / drive
    s = np.concatenate([[0.0], svc])
    max_t = C.ROUTE_MAX_HOURS[mode] * 3600
    routes = clarke_wright(T, s, max_t)
    routes = [two_opt(r, T) for r in routes]
    routes = relocate(routes, T, s, max_t)
    routes = [two_opt(r, T) for r in routes]
    hours = sum(_route_time(r, T, s) for r in routes) / 3600
    vehicle_km = 0.0
    for r in routes:
        seq = [0] + r + [0]
        legs = D[seq[:-1], seq[1:]]
        vehicle_km += (legs.sum() if mode == "drive" else legs[0] + legs[-1]) / 1000
    return {"routes": routes, "hours": hours, "vehicle_km": vehicle_km, "n_routes": len(routes)}


def _svc_lobby(units):
    return C.SERVICE_SEC["lobby_base"] + C.SERVICE_SEC["lobby_per_unit"] * units


def _svc_cmb(load):
    return C.SERVICE_SEC["cmb_base"] + C.SERVICE_SEC["cmb_per_unit"] * load


def _daily_cost(*parts):
    return sum(p["hours"] * C.LOADED_LABOUR_COST_PER_HOUR + p["vehicle_km"] * C.VEHICLE_COST_PER_KM for p in parts)


def _r(v):
    return round(float(v), 1)


def _solve(area, depot):
    """Before/after for one area (or carrier zone)."""
    door = np.where(area.kind == "door")[0]
    cmb = np.where(area.kind == "cmb")[0]
    lobby = np.where(area.kind == "lobby")[0]
    existing = site_cmbs(area, cmb) if len(cmb) else None
    converted = site_cmbs(area, np.concatenate([door, cmb])) if len(door) + len(cmb) else None
    m = area.metric
    py = area.plot_y()

    walk = solve_routes(area.x[door], area.sy[door], area.off[door],
                        np.full(len(door), C.SERVICE_SEC["door"], float), "walk", m, depot)
    ex = existing or {"x": [], "y": [], "off": [], "load": np.array([])}
    before_drive = solve_routes(np.concatenate([area.x[lobby], ex["x"]]), np.concatenate([area.sy[lobby], ex["y"]]),
                                np.concatenate([area.off[lobby], ex["off"]]),
                                np.concatenate([_svc_lobby(area.units[lobby]), _svc_cmb(ex["load"])]), "drive", m, depot)
    cv = converted or {"x": np.array([]), "y": np.array([]), "off": np.array([]), "load": np.array([])}
    ax, ay = np.concatenate([area.x[lobby], cv["x"]]), np.concatenate([area.sy[lobby], cv["y"]])
    after = solve_routes(ax, ay, np.concatenate([area.off[lobby], cv["off"]]),
                         np.concatenate([_svc_lobby(area.units[lobby]), _svc_cmb(cv["load"])]), "drive", m, depot)

    def paths(res, xs, ys):
        px = np.concatenate([[depot[0]], xs]); pyy = np.concatenate([[depot[1]], ys])
        return [[[_r(px[k]), _r(pyy[k])] for k in [0] + r + [0]] for r in res["routes"]]

    return {
        "door": len(door), "cmb": len(cmb), "lobby": len(lobby), "lobby_units": int(area.units[lobby].sum()),
        "households": int(area.units.sum()),
        "sites_existing": len(existing["x"]) if existing else 0, "sites_after": len(cv["x"]),
        "walk_sum": converted["walk_sum_m"] if converted else 0.0, "walk_n": converted["n"] if converted else 0,
        "walk_max": converted["max_walk_m"] if converted else 0.0,
        "walk": walk, "before_drive": before_drive, "after": after,
        "plot": {
            "points": {k: [[_r(a), _r(b)] for a, b in zip(area.x[i], py[i])] for k, i in
                       (("door", door), ("cmb", cmb), ("lobby", lobby))},
            "sites_after": [[_r(a), _r(b), int(l)] for a, b, l in zip(cv["x"], cv["y"], cv["load"])],
            "routes_before_walk": paths(walk, area.x[door], py[door]),
            "routes_after": paths(after, ax, np.concatenate([py[lobby], cv["y"]])),
        },
    }


def _result(row, parts, depot, scale, source, extra=None):
    tot = lambda key, f: sum(f(p[key]) for p in parts)
    walk_h, walk_r = tot("walk", lambda r: r["hours"]), tot("walk", lambda r: r["n_routes"])
    bd_h, bd_r = tot("before_drive", lambda r: r["hours"]), tot("before_drive", lambda r: r["n_routes"])
    af_h, af_r = tot("after", lambda r: r["hours"]), tot("after", lambda r: r["n_routes"])
    km_b = tot("walk", lambda r: r["vehicle_km"]) + tot("before_drive", lambda r: r["vehicle_km"])
    km_a = tot("after", lambda r: r["vehicle_km"])
    cost_b = (walk_h + bd_h) * C.LOADED_LABOUR_COST_PER_HOUR + km_b * C.VEHICLE_COST_PER_KM
    cost_a = af_h * C.LOADED_LABOUR_COST_PER_HOUR + km_a * C.VEHICLE_COST_PER_KM
    walk_n = sum(p["walk_n"] for p in parts)
    plot = {"depot": [_r(depot[0]), _r(depot[1])], "points": {"door": [], "cmb": [], "lobby": []},
            "sites_after": [], "routes_before_walk": [], "routes_after": []}
    for p in parts:
        for k in plot["points"]:
            plot["points"][k] += p["plot"]["points"][k]
        for k in ("sites_after", "routes_before_walk", "routes_after"):
            plot[k] += p["plot"][k]
    out = {
        "fsa": row["fsa"], "province": row["province"], "source": source,
        "sample_households": sum(p["households"] for p in parts), "scale_factor": scale, "zones": len(parts),
        "mix": {"door": sum(p["door"] for p in parts), "existing_cmb": sum(p["cmb"] for p in parts),
                "lobby_buildings": sum(p["lobby"] for p in parts), "lobby_units": sum(p["lobby_units"] for p in parts)},
        "cmb_sites_existing": sum(p["sites_existing"] for p in parts),
        "cmb_sites_after": sum(p["sites_after"] for p in parts),
        "mean_walk_to_cmb_m": sum(p["walk_sum"] for p in parts) / max(walk_n, 1),
        "max_walk_to_cmb_m": max(p["walk_max"] for p in parts),
        "before": {"walk_routes": walk_r, "walk_hours": walk_h, "drive_routes": bd_r, "drive_hours": bd_h,
                   "vehicle_km": km_b, "daily_cost": cost_b},
        "after": {"drive_routes": af_r, "drive_hours": af_h, "vehicle_km": km_a, "daily_cost": cost_a},
        "daily_saving_sample": cost_b - cost_a,
        "annual_saving_fsa_bottom_up": (cost_b - cost_a) * C.WORKING_DAYS_PER_YEAR * scale,
        "plot": plot,
    }
    out.update(extra or {})
    return out


def optimize_fsa(row, n_points=900, seed=0):
    """Synthetic-grid case study, scaled to the whole FSA."""
    area = synth_area(row, n_points, seed)
    part = _solve(area, DEPOT)
    return _result(row, [part], DEPOT, _modelled_points(row) / part["households"], "synthetic street grid")


ROAD_BUFFER = 800.0   # m of street network kept around each carrier zone


def optimize_real_fsa(row, locs, seed=0, depot=None, source="NAR real addresses"):
    """Whole-FSA run on real addresses, zone by zone from the FSA's delivery depot.

    depot: dict with lat, lon, name, geocode for the Canada Post installation serving the FSA.
    With NAR coordinates (EPSG:3347) and the Road Network File present, distances inside each
    carrier zone are shortest paths on real streets; depot legs stay straight line x circuity.
    """
    from . import roads
    ll = (depot["lat"], depot["lon"]) if depot else None
    area, dxy, coverage, matched, origin = real_area(row, locs, seed, ll)
    zs = zones(area, seed=seed)
    net_stats = None
    if origin is not None and roads.available():
        b = ROAD_BUFFER
        geoms = roads.read_roads((area.x.min() + origin[0] - b, area.sy.min() + origin[1] - b,
                                  area.x.max() + origin[0] + b, area.sy.max() + origin[1] + b))
        net_stats = {"segments": int(len(geoms)), "nodes": 0, "edges": 0}
    parts = []
    for z in zs:
        sub = area.subset(z)
        if net_stats is not None:
            box = shapely.box(sub.x.min() + origin[0] - ROAD_BUFFER, sub.sy.min() + origin[1] - ROAD_BUFFER,
                              sub.x.max() + origin[0] + ROAD_BUFFER, sub.sy.max() + origin[1] + ROAD_BUFFER)
            net = roads.RoadNetwork(geoms[shapely.intersects(geoms, box)], origin)
            net_stats["nodes"] += net.n_nodes
            net_stats["edges"] += net.n_edges
            sub.metric = net
        parts.append(_solve(sub, dxy))
    modelled = sum(p["households"] for p in parts)
    res = _result(row, parts, dxy, _modelled_points(row) / modelled, source,
                  {"oda_coverage": coverage, "oda_locations": int(len(locs)), "postal_match_rate": matched,
                   "distance_model": "road network (StatCan RNF 2021)" if net_stats else "straight line x 1.3",
                   "road_network": net_stats,
                   "depot_name": depot["name"] if depot else "address centroid (no depot match)",
                   "depot_geocode": depot["geocode"] if depot else None})
    lc = row.get("cp_lc_routes")
    if lc and lc == lc:
        b = res["before"]
        res["cp_routes"] = {"lc": int(lc), "ss": int(row.get("cp_ss_routes") or 0)}
        res["model_hours_per_cp_route"] = (b["walk_hours"] + b["drive_hours"]) / (lc + (row.get("cp_ss_routes") or 0))
    return res
