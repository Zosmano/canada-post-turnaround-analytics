"""Street-network distances from the Statistics Canada 2021 Road Network File (EPSG:3347).

Road segments are densified every 25 m so homes snap to the street beside them rather than to
the nearest intersection; consecutive vertices become graph edges weighted by length.
Distances are shortest paths (Dijkstra, computed per source on demand and cached) plus the
walk from the sidewalk (6 m off the centreline) to the building at each end. Points more than 300 m from any road,
or in a disconnected piece of the network, fall back to straight line x circuity.
"""
import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .config import ROAD_CIRCUITY, ROOT

RNF_ZIP = ROOT / "lrnf000r21a_e.zip"
SPACING = 25.0
SNAP_MAX = 300.0
SIDEWALK = 6.0        # m from road centreline to sidewalk


def available():
    return RNF_ZIP.exists()


def read_roads(bbox):
    """Road geometries intersecting bbox (xmin, ymin, xmax, ymax) in EPSG:3347."""
    import pyogrio
    df = pyogrio.read_dataframe(f"zip://{RNF_ZIP}!lrnf000r21a_e.shp", bbox=tuple(bbox), columns=["CLASS"])
    return shapely.get_parts(df.geometry.values)


class RoadNetwork:
    def __init__(self, geoms, origin=(0.0, 0.0)):
        geoms = shapely.segmentize(geoms, SPACING)
        coords, part = shapely.get_coordinates(geoms, return_index=True)
        coords = coords - np.asarray(origin)
        key = np.round(coords, 1)
        uniq, node = np.unique(key, axis=0, return_inverse=True)
        node = node.ravel()
        same = part[1:] == part[:-1]
        a, b = node[:-1][same], node[1:][same]
        w = np.hypot(*(coords[1:][same] - coords[:-1][same]).T)
        keep = a != b
        a, b, w = a[keep], b[keep], w[keep]
        n = len(uniq)
        self.graph = coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr()
        self.xy = uniq
        self.tree = cKDTree(uniq)
        self.rows = {}
        self.n_nodes, self.n_edges = n, len(w)

    def snap(self, x, y):
        d, i = self.tree.query(np.c_[x, y])
        return i, d

    def _rows(self, sources):
        need = [s for s in dict.fromkeys(sources.tolist()) if s not in self.rows]
        for k in range(0, len(need), 256):
            batch = need[k:k + 256]
            res = dijkstra(self.graph, directed=False, indices=batch).astype(np.float32)
            for s, r in zip(batch, res):
                self.rows[s] = r
        return np.stack([self.rows[s] for s in sources]) if len(sources) else np.zeros((0, self.n_nodes), np.float32)

    def distance(self, xa, ya, oa, xb, yb, ob):
        xa, ya, oa, xb, yb, ob = (np.asarray(v, float) for v in (xa, ya, oa, xb, yb, ob))
        ia, da = self.snap(xa, ya)
        ib, db = self.snap(xb, yb)
        net = self._rows(ia)[:, ib].astype(float)
        # the driveway leg is measured to the sidewalk, not the road centreline
        wa, wb = np.clip(da - SIDEWALK, 0, None), np.clip(db - SIDEWALK, 0, None)
        D = net + wa[:, None] + wb[None, :] + oa[:, None] + ob[None, :]
        straight = ROAD_CIRCUITY * np.hypot(xa[:, None] - xb[None, :], ya[:, None] - yb[None, :]) + oa[:, None] + ob[None, :]
        bad = (da > SNAP_MAX)[:, None] | (db > SNAP_MAX)[None, :] | ~np.isfinite(net)
        D[bad] = straight[bad]
        return D
