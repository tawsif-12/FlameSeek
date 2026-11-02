"""Step 4: group footprints into fire events.

A. Daily clustering. On the same day, two detections are linked when their
   footprints overlap OR their centroid distance (in UTM, zone picked
   automatically for each pair) is at most the sum of their half-diagonals.
   Connected components of that graph (networkx) are daily clusters.
B. Multi-day linking. Detections on consecutive days are linked when their
   footprints overlap. Two daily clusters overlap exactly when some pair of
   their footprints overlaps, so this equals cluster-level linking.
C. Anti-chaining caps. Events wider than cap_extent_km or longer than
   cap_duration_days are split and counted.
D. FRP is summed only within one overpass (same platform, same acquisition
   time). Across overpasses the maximum and mean are reported, never a sum.
E. p_conf_fused = 1 - prod(1 - p_k).

Distances use UTM; areas use EPSG:6933.
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial import ConvexHull
from scipy.spatial.distance import pdist
from sklearn.neighbors import BallTree

from pipeline.footprints import _TO_6933

EARTH_R_KM = 6371.0088
_FROM_6933 = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
_utm_cache: dict[int, Transformer] = {}


# ---------------------------------------------------------------- helpers ----
def utm_epsg(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """UTM EPSG code for each point (326zz north, 327zz south)."""
    lon = (np.asarray(lon) + 180) % 360 - 180
    zone = np.clip(np.floor((lon + 180) / 6).astype(int) + 1, 1, 60)
    return np.where(np.asarray(lat) >= 0, 32600, 32700) + zone


def utm_transformer(epsg: int) -> Transformer:
    if epsg not in _utm_cache:
        _utm_cache[epsg] = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return _utm_cache[epsg]


def midpoint(lon1, lat1, lon2, lat2):
    """Great-circle midpoint (safe across the antimeridian)."""
    l1, p1, l2, p2 = map(np.radians, (lon1, lat1, lon2, lat2))
    x = np.cos(p1) * np.cos(l1) + np.cos(p2) * np.cos(l2)
    y = np.cos(p1) * np.sin(l1) + np.cos(p2) * np.sin(l2)
    z = np.sin(p1) + np.sin(p2)
    return np.degrees(np.arctan2(y, x)), np.degrees(np.arctan2(z, np.hypot(x, y)))


def utm_distance_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    """Distance between point pairs, each pair projected to the UTM zone of its midpoint."""
    mlon, mlat = midpoint(lon1, lat1, lon2, lat2)
    epsg = utm_epsg(mlon, mlat)
    out = np.empty(len(lon1))
    for code in np.unique(epsg):
        m = epsg == code
        t = utm_transformer(int(code))
        x1, y1 = t.transform(lon1[m], lat1[m])
        x2, y2 = t.transform(lon2[m], lat2[m])
        out[m] = np.hypot(x2 - x1, y2 - y1) / 1000.0
    return out


def extent_km(geoms: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> float:
    """Largest corner-to-corner distance of the footprints, in the UTM zone of their centre."""
    clon, clat = midpoint(lon.min(), lat.mean(), lon.max(), lat.mean())
    t = utm_transformer(int(utm_epsg(clon, clat)))
    xy = shapely.get_coordinates(geoms)
    x, y = t.transform(xy[:, 0], xy[:, 1])
    pts = np.unique(np.c_[x, y].round(1), axis=0)
    if len(pts) > 3:
        try:
            pts = pts[ConvexHull(pts).vertices]
        except Exception:  # degenerate (collinear) hull: use all points
            pass
    return float(pdist(pts).max() / 1000.0) if len(pts) > 1 else 0.0


# ------------------------------------------------------------ link graph -----
def daily_links(day: gpd.GeoDataFrame) -> pd.DataFrame:
    """Pairs of same-day detections that overlap or sit within the half-diagonal sum."""
    if len(day) < 2:
        return pd.DataFrame(columns=["i", "j", "dist_km", "overlap", "within_halfdiag"])
    lat, lon = day["latitude"].to_numpy(), day["longitude"].to_numpy()
    hd = day["half_diag_km"].to_numpy()
    tree = BallTree(np.radians(np.c_[lat, lon]), metric="haversine")
    # Candidate radius: the largest possible half-diagonal sum, plus 2% margin.
    r = 2 * hd.max() * 1.02 / EARTH_R_KM
    neigh = tree.query_radius(np.radians(np.c_[lat, lon]), r=r)
    i = np.repeat(np.arange(len(day)), [len(n) for n in neigh])
    j = np.concatenate(neigh)
    keep = i < j
    i, j = i[keep], j[keep]
    if len(i) == 0:
        return pd.DataFrame(columns=["i", "j", "dist_km", "overlap", "within_halfdiag"])
    d = utm_distance_km(lon[i], lat[i], lon[j], lat[j])
    geoms = day.geometry.to_numpy()
    overlap = shapely.intersects(geoms[i], geoms[j])
    within = d <= hd[i] + hd[j]
    linked = overlap | within
    ids = day["det_id"].to_numpy()
    return pd.DataFrame({"i": ids[i[linked]], "j": ids[j[linked]], "dist_km": d[linked],
                         "overlap": overlap[linked], "within_halfdiag": within[linked]})


def consecutive_day_links(gdf: gpd.GeoDataFrame, day_col: str) -> pd.DataFrame:
    """Footprint overlaps between detections on day d and day d+1."""
    days = sorted(gdf[day_col].unique())
    out = []
    for d0, d1 in zip(days[:-1], days[1:]):
        if (pd.Timestamp(d1) - pd.Timestamp(d0)).days != 1:
            continue
        a, b = gdf[gdf[day_col] == d0], gdf[gdf[day_col] == d1]
        tree = shapely.STRtree(b.geometry.to_numpy())
        ia, ib = tree.query(a.geometry.to_numpy(), predicate="intersects")
        out.append(pd.DataFrame({"i": a["det_id"].to_numpy()[ia], "j": b["det_id"].to_numpy()[ib]}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["i", "j"])


# ------------------------------------------------------------------ caps -----
def split_by_caps(members: np.ndarray, graph: nx.Graph, gdf: gpd.GeoDataFrame,
                  day_col: str, cap_km: float, cap_days: int) -> tuple[list[np.ndarray], list[str]]:
    """Split one component until every piece respects both caps."""
    reasons = []
    sub = gdf.loc[members]
    pieces = [members]

    # Duration cap: cut into windows of cap_days, then re-take connected components.
    days = pd.to_datetime(sub[day_col])
    if (days.max() - days.min()).days + 1 > cap_days:
        reasons.append("duration")
        window = ((days - days.min()).dt.days // cap_days).to_numpy()
        pieces = []
        for w in np.unique(window):
            ids = members[window == w]
            pieces += [np.array(sorted(c)) for c in nx.connected_components(graph.subgraph(ids))]

    # Extent cap: complete-linkage clustering of centroids with threshold
    # cap - 2*max half-diagonal guarantees each piece's footprint extent <= cap.
    final = []
    for ids in pieces:
        g = gdf.loc[ids]
        if len(ids) < 2 or extent_km(g.geometry.to_numpy(), g["longitude"].to_numpy(),
                                     g["latitude"].to_numpy()) <= cap_km:
            final.append(ids)
            continue
        if "extent" not in reasons:
            reasons.append("extent")
        t = utm_transformer(int(utm_epsg(g["longitude"].median(), g["latitude"].median())))
        x, y = t.transform(g["longitude"].to_numpy(), g["latitude"].to_numpy())
        thr = (cap_km - 2 * g["half_diag_km"].max()) * 1000.0
        labels = fcluster(linkage(np.c_[x, y], method="complete"), t=thr, criterion="distance")
        for lab in np.unique(labels):
            part = ids[labels == lab]
            final += [np.array(sorted(c)) for c in nx.connected_components(graph.subgraph(part))]
    return final, reasons


# ------------------------------------------------------------ aggregation ----
def union_area_centroid(geoms: np.ndarray, ref_lon: float) -> tuple[float, float, float]:
    """Area (km2, EPSG:6933) and centroid of the union of footprints."""
    xy = shapely.get_coordinates(geoms)
    x, y = _TO_6933.transform(xy[:, 0] - ref_lon, xy[:, 1])
    proj = shapely.set_coordinates(shapely.transform(geoms, lambda c: c), np.c_[x, y])
    u = shapely.union_all(proj)
    c = u.centroid
    clon, clat = _FROM_6933.transform(c.x, c.y)
    return u.area / 1e6, (clon + ref_lon + 180) % 360 - 180, clat


def fused(p: pd.Series) -> float:
    return float(1 - np.prod(1 - p.to_numpy()))


def build_tables(gdf: gpd.GeoDataFrame, cfg: dict, day_col: str):
    # Per-overpass FRP: summed only within one platform + one acquisition time.
    ov = (gdf.groupby(["fire_id", "sensor", "platform", "acq_datetime_utc"])
             .agg(n_detections=("det_id", "size"), frp_sum_mw=("frp_mw", "sum"),
                  p_conf_fused=("p_conf", fused), bt_max_k=("bt_k", "max"))
             .reset_index())

    d = pd.DataFrame(gdf.drop(columns="geometry"))
    d["is_m"] = d["sensor"].eq("MODIS").astype(int)
    d["is_v"] = d["sensor"].eq("VIIRS").astype(int)
    d["log1mp"] = np.log1p(-d["p_conf"].clip(upper=1 - 1e-12))  # for p_fused = 1 - prod(1-p)
    g = d.groupby("fire_id", sort=True)
    ev = g.agg(start_time=("acq_datetime_utc", "min"), end_time=("acq_datetime_utc", "max"),
               n_days=(day_col, "nunique"), n_detections=("det_id", "size"),
               n_MODIS=("is_m", "sum"), n_VIIRS=("is_v", "sum"),
               platforms_seen=("platform", lambda s: ";".join(sorted(set(s)))),
               log1mp=("log1mp", "sum"), p_conf_max=("p_conf", "max"),
               extent_km=("extent_km", "first"), raw_event=("raw_event", "first"),
               was_split=("was_split", "first"), split_reason=("split_reason", "first"))
    ev["n_overpasses"] = ov.groupby("fire_id").size()
    ev["sensor_flag"] = np.where((ev["n_MODIS"] > 0) & (ev["n_VIIRS"] > 0), "both",
                                 np.where(ev["n_MODIS"] > 0, "MODIS_only", "VIIRS_only"))
    ev["p_conf_fused"] = 1 - np.exp(ev.pop("log1mp"))

    # Footprint union area and centroid. Singletons: the footprint itself.
    single = ev["n_detections"] == 1
    s = gdf[gdf["fire_id"].isin(ev.index[single])].set_index("fire_id")
    ev.loc[single, "footprint_area_km2"] = s["footprint_area_km2"]
    ev.loc[single, "centroid_lat"] = s["latitude"]
    ev.loc[single, "centroid_lon"] = s["longitude"]
    multi = gdf[gdf["fire_id"].isin(ev.index[~single])]
    res = {fid: union_area_centroid(grp.geometry.to_numpy(), float(grp["longitude"].iloc[0]))
           for fid, grp in multi.groupby("fire_id")}
    if res:
        r = pd.DataFrame(res, index=["footprint_area_km2", "centroid_lon", "centroid_lat"]).T
        ev.loc[r.index, ["footprint_area_km2", "centroid_lon", "centroid_lat"]] = r.values

    # FRP: max and mean of per-overpass sums, per sensor. Never a sum across overpasses.
    for sensor, tag in (("MODIS", "MODIS"), ("VIIRS", "VIIRS")):
        o = ov[ov["sensor"] == sensor].groupby("fire_id")["frp_sum_mw"]
        ev[f"FRP_{tag}_max"] = o.max()
        ev[f"FRP_{tag}_mean_overpass"] = o.mean()
    ev["biome"] = np.nan  # MCD12Q1 not available yet; left empty, not guessed
    ev["split_from"] = np.where(ev.pop("was_split"), ev["raw_event"], "")
    ev = ev.drop(columns="raw_event")
    ev["data_version"], ev["processing_date"] = cfg["data_version"], cfg["processing_date"]
    cols = ["start_time", "end_time", "n_days", "n_detections", "n_MODIS", "n_VIIRS", "n_overpasses",
            "platforms_seen", "sensor_flag", "p_conf_fused", "p_conf_max", "centroid_lat", "centroid_lon",
            "footprint_area_km2", "extent_km", "FRP_MODIS_max", "FRP_VIIRS_max",
            "FRP_MODIS_mean_overpass", "FRP_VIIRS_mean_overpass", "biome", "split_from", "split_reason",
            "data_version", "processing_date"]
    return ev[cols].reset_index(), ov


def matched_pairs(ov: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Aqua with S-NPP/NOAA-20 overpasses of the same event within the window. Terra never used."""
    e = cfg["events"]
    if "Terra" in e["matched_pair_modis"]:
        raise ValueError("Terra must never be paired with VIIRS (procedure rule 2)")
    m = ov[ov["platform"].isin(e["matched_pair_modis"])]
    v = ov[ov["platform"].isin(e["matched_pair_viirs"])]
    pairs = m.merge(v, on="fire_id", suffixes=("_modis", "_viirs"))
    if pairs.empty:
        return pairs.assign(dt_min=pd.Series(dtype=float), window_min=pd.Series(dtype=float))
    pairs["window_min"] = pairs["platform_viirs"].map(window_by_platform(cfg)).astype(float)
    # Signed: VIIRS time minus Aqua time, in minutes.
    pairs["dt_min"] = (pairs["acq_datetime_utc_viirs"] - pairs["acq_datetime_utc_modis"]).dt.total_seconds() / 60
    return pairs[pairs["dt_min"].abs() <= pairs["window_min"]].reset_index(drop=True)


def window_by_platform(cfg: dict) -> dict:
    """Matching window (min) per VIIRS platform, never above the configured maximum."""
    e = cfg["events"]
    cap = e.get("matched_pair_window_max_min", 60)
    per = e.get("matched_pair_window_by_platform", {}) or {}
    return {p: min(per.get(p, e["matched_pair_window_min"]), cap) for p in ("S-NPP", "NOAA-20", "NOAA-21")}


# ------------------------------------------------------- fast helpers --------
def component_labels(graph: nx.Graph, pos: pd.Series) -> np.ndarray:
    """networkx connected components as one integer label per detection (row order)."""
    labels = np.empty(len(pos), dtype=np.int64)
    for k, c in enumerate(nx.connected_components(graph)):
        labels[pos[list(c)].to_numpy()] = k
    return labels


def cap_candidates(gdf, comp, day_col, cap_km, cap_days) -> list[int]:
    """Components that might break a cap. A cheap lat/lon bounding-box bound
    (over-estimates width; any antimeridian span is always a candidate) picks
    them; split_by_caps then applies the exact test."""
    df = pd.DataFrame({"c": comp, "lat": gdf["latitude"].to_numpy(), "lon": gdf["longitude"].to_numpy(),
                       "hd": gdf["half_diag_km"].to_numpy(),
                       "day": pd.to_datetime(gdf[day_col]).to_numpy()})
    a = df.groupby("c").agg(n=("lat", "size"), lat0=("lat", "min"), lat1=("lat", "max"),
                            lon0=("lon", "min"), lon1=("lon", "max"), hd=("hd", "max"),
                            d0=("day", "min"), d1=("day", "max"))
    a = a[a["n"] > 1]
    coslat = np.cos(np.radians(np.minimum(np.abs(a["lat0"]), np.abs(a["lat1"]))))
    wide = np.hypot((a["lon1"] - a["lon0"]) * 111.4 * coslat, (a["lat1"] - a["lat0"]) * 111.4)
    bound = wide + 2 * a["hd"] + 0.5  # +0.5 km margin for rotation/ellipsoid
    days = (a["d1"] - a["d0"]).dt.days + 1
    return a.index[(bound > cap_km) | (days > cap_days)].tolist()


def piece_extents(gdf, piece: np.ndarray) -> np.ndarray:
    """Extent (km) of every event: corner-to-corner maximum in UTM; singletons = pixel diagonal."""
    out = 2 * gdf["half_diag_km"].to_numpy().astype(float)
    sizes = np.bincount(piece)
    multi = np.flatnonzero(sizes[piece] > 1)
    if len(multi) == 0:
        return out
    order = multi[np.argsort(piece[multi], kind="stable")]
    geoms = gdf.geometry.to_numpy()
    lon, lat = gdf["longitude"].to_numpy(), gdf["latitude"].to_numpy()
    bounds = np.flatnonzero(np.diff(piece[order])) + 1
    for rows in np.split(order, bounds):
        out[rows] = extent_km(geoms[rows], lon[rows], lat[rows])
    return out


# -------------------------------------------------------------------- run ----
def run(fp: gpd.GeoDataFrame, cfg: dict) -> dict:
    e = cfg["events"]
    day_col = "local_solar_date" if e.get("day_basis", "local_solar") == "local_solar" else "utc_date"
    gdf = fp.set_index("det_id", drop=False)

    # A. Daily links.
    daily = pd.concat([daily_links(g) for _, g in gdf.groupby(day_col)], ignore_index=True)
    g_daily = nx.Graph()
    g_daily.add_nodes_from(gdf.index)
    g_daily.add_edges_from(daily[["i", "j"]].itertuples(index=False, name=None))
    pos = pd.Series(np.arange(len(gdf)), index=gdf.index)
    gdf["daily_cluster"] = component_labels(g_daily, pos)

    # B. Multi-day links.
    multi = consecutive_day_links(gdf, day_col)
    graph = g_daily.copy()
    graph.add_edges_from(multi[["i", "j"]].itertuples(index=False, name=None))

    # C. Components, then anti-chaining caps.
    comp = component_labels(graph, pos)
    n_raw = int(comp.max()) + 1
    piece = comp.copy()
    was_split = np.zeros(len(gdf), bool)
    split_reason = np.full(len(gdf), "", dtype=object)
    n_split, split_reasons = 0, {"extent": 0, "duration": 0}
    for k in cap_candidates(gdf, comp, day_col, e["cap_extent_km"], e["cap_duration_days"]):
        members = gdf.index.to_numpy()[comp == k]
        pieces, reasons = split_by_caps(members, graph, gdf, day_col, e["cap_extent_km"],
                                        e["cap_duration_days"])
        if len(pieces) < 2:
            continue
        n_split += 1
        for r in reasons:
            split_reasons[r] += 1
        nxt = piece.max() + 1
        for j, p in enumerate(pieces[1:]):  # first piece keeps the component's label
            piece[pos[p].to_numpy()] = nxt + j
        idx = pos[members].to_numpy()
        was_split[idx], split_reason[idx] = True, "+".join(reasons)
    gdf["raw_event"] = [f"RAW{c:07d}" for c in comp]
    gdf["was_split"], gdf["split_reason"] = was_split, split_reason

    # Stable fire ids ordered by first detection time, then mean latitude.
    key = (pd.DataFrame({"piece": piece, "t": gdf["acq_datetime_utc"].to_numpy(),
                         "lat": gdf["latitude"].to_numpy()})
           .groupby("piece").agg(t=("t", "min"), lat=("lat", "mean")).sort_values(["t", "lat"]))
    rank = pd.Series(np.arange(1, len(key) + 1), index=key.index)
    gdf["fire_id"] = [f"FE{n:07d}" for n in rank[piece].to_numpy()]
    gdf["extent_km"] = piece_extents(gdf, piece)

    events, ov = build_tables(gdf, cfg, day_col)
    pairs = matched_pairs(ov, cfg)
    stats = {"n_detections": len(gdf), "n_daily_links": len(daily),
             "n_links_overlap": int(daily["overlap"].sum()),
             "n_links_halfdiag_only": int((~daily["overlap"] & daily["within_halfdiag"]).sum()),
             "n_multiday_links": len(multi), "n_raw_components": n_raw,
             "n_events": len(events), "n_events_split": n_split,
             "n_split_by_extent": split_reasons["extent"],
             "n_split_by_duration": split_reasons["duration"],
             "n_pieces_from_splits": int(gdf.loc[gdf["was_split"], "fire_id"].nunique()),
             "n_matched_pairs": len(pairs),
             "n_events_with_matched_pair": int(pairs["fire_id"].nunique()) if len(pairs) else 0,
             "day_basis": day_col}
    print(f"[Step 4] {len(gdf)} detections -> {len(events)} fire events "
          f"({n_split} components split by caps: {split_reasons}); "
          f"Aqua-VIIRS pairs within {e['matched_pair_window_min']} min: {len(pairs)}")
    return {"detections": gdf.reset_index(drop=True), "events": events,
            "overpasses": ov, "pairs": pairs, "stats": stats}
