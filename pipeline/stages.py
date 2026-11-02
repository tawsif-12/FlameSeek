"""Day-by-day stages for Steps 1-5 (scalable layout; results match the batch pipeline).

  raw_split  window -> raw_daily/<UTC day>/part-*.parquet + window manifest
             (bbox, partial days, era measurements). One pass over the raw files.
  detect     local solar day D (parallel): ingest + quality + region filter + footprints +
             daily clustering -> detections, lowconf, removed, day_stats
  link       day D (sequential, reads only day D-1): multi-day linking and caps ->
             assign (det -> fire_id), event_state (hull per active event), merges
  grid       day D (parallel): area-weighted 0.1° grid -> grid_overpass, grid_cellday
  finalize   window: resolve merges, build the window tables with DuckDB + pandas.

Rows are assigned to the local solar day of the detection (decisions.md D12). A local day
spans UTC days D-1..D+1, so `detect` reads those three raw parts. Each detection keeps a
stable id (hash of source file and row), so reruns give identical partitions.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely

from pipeline import eras as eras_mod
from pipeline import events as ev_mod
from pipeline import footprints, grid, ingest, quality
from pipeline import partitions as P
from pipeline.inspect_raw import PLATFORM_CODES, parse_acq_date, read_firms_csv

DAY_COL = "local_solar_date"


# ----------------------------------------------------------------- helpers ---
def stable_ids(files: pd.Series, rows: pd.Series) -> np.ndarray:
    """64-bit id from (source file, source row): identical on every run."""
    return np.array([int.from_bytes(hashlib.blake2b(f"{f}:{r}".encode(), digest_size=8).digest(),
                                    "little", signed=True) for f, r in zip(files, rows)], dtype=np.int64)


def manifest_path(cfg) -> Path:
    return cfg["paths"]["window_interim"] / "manifest.json"


def load_manifest(cfg) -> dict:
    m = json.loads(manifest_path(cfg).read_text())
    m["coverage"] = {k: (pd.Timestamp(v) if v else None) for k, v in m["coverage"].items()}
    return m


def local_days(cfg) -> list[date]:
    w = cfg["window"]
    return P.days(w["start"] - timedelta(days=1), w["end"] + timedelta(days=1))


def read_raw_days(root, utc_days) -> pd.DataFrame:
    frames = []
    for d in utc_days:
        dd = P.part_dir(root, "raw_daily", d)
        if dd.exists():
            frames += [pd.read_parquet(f) for f in sorted(dd.glob("part-*.parquet"))]
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True, sort=False)
    return raw.sort_values(["source_file", "source_row"], kind="stable").reset_index(drop=True)


# --------------------------------------------------------------- raw split ---
def raw_split(cfg: dict, force: bool = False) -> dict:
    """Split the window's raw CSVs into UTC-day parts and write the window manifest."""
    w, root = cfg["window"], cfg["paths"]["partition_root"]
    mpath = manifest_path(cfg)
    utc_days = P.days(w["start"], w["end"])
    done = all((P.part_dir(root, "raw_daily", d) / "_SUCCESS").exists() for d in utc_days)
    if done and mpath.exists() and not force:
        return load_manifest(cfg)
    files = sorted(Path(w["raw_dir"]).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No raw CSV files in {w['raw_dir']} for window {w['name']}")
    for d in utc_days:  # clear old parts of this window's days
        dd = P.part_dir(root, "raw_daily", d)
        if dd.exists():
            for f in dd.glob("*"):
                f.unlink()
    counts: dict[str, int] = {}
    hist: dict[tuple, np.ndarray] = {}
    presence: dict[tuple, int] = {}
    bounds = [np.inf, np.inf, -np.inf, -np.inf]
    undated = []
    lat_band = cfg["eras"]["lat_band"]
    chunk_rows = cfg["partitions"]["raw_chunk_rows"]
    for fi, f in enumerate(files):
        df_all = read_firms_csv(f)
        df_all["source_file"] = f.name
        df_all["source_row"] = np.arange(len(df_all)) + 2
        for ci, s0 in enumerate(range(0, len(df_all), chunk_rows)):
            df = df_all.iloc[s0:s0 + chunk_rows].copy()
            d = parse_acq_date(df["acq_date"])
            undated.append(df[d.isna()])
            df, d = df[d.notna()], d[d.notna()]
            inwin = (d.dt.date >= w["start"]) & (d.dt.date <= w["end"])
            df, d = df[inwin], d[inwin]
            ok = df["latitude"].notna() & df["longitude"].notna()
            if ok.any():
                bounds = [min(bounds[0], df.loc[ok, "longitude"].min()), min(bounds[1], df.loc[ok, "latitude"].min()),
                          max(bounds[2], df.loc[ok, "longitude"].max()), max(bounds[3], df.loc[ok, "latitude"].max())]
            # Era measurement: minute histogram of daytime LST per platform and month (exact
            # median at 1-min resolution without keeping every value; scales to years).
            plat = df["satellite"].astype(str).str.strip().map(PLATFORM_CODES)
            month = d.dt.strftime("%Y-%m")
            for (p, m), n in pd.Series(1, index=[plat, month]).groupby(level=[0, 1]).sum().items():
                presence[(p, m)] = presence.get((p, m), 0) + int(n)
            hhmm = pd.to_numeric(df["acq_time"], errors="coerce")
            lst_min = ((hhmm // 100) * 60 + hhmm % 100 + df["longitude"] * 4) % 1440
            day_m = (df["daynight"].astype(str).str.upper() == "D") & (df["latitude"].abs() <= lat_band) & lst_min.notna()
            for (p, m), g in lst_min[day_m].groupby([plat[day_m], month[day_m]]):
                h = hist.setdefault((p, m), np.zeros(1440, dtype=np.int64))
                h += np.bincount(g.astype(int).clip(0, 1439), minlength=1440)
            for day, g in df.groupby(d.dt.date):
                counts[str(day)] = counts.get(str(day), 0) + len(g)
                out = P.part_dir(root, "raw_daily", day)
                out.mkdir(parents=True, exist_ok=True)
                g.to_parquet(out / f"part-{fi:03d}-{ci:04d}.parquet", index=False)
    for d in utc_days:
        dd = P.part_dir(root, "raw_daily", d)
        dd.mkdir(parents=True, exist_ok=True)
        (dd / "_SUCCESS").write_text("")
    undated = pd.concat(undated, ignore_index=True) if undated else pd.DataFrame()
    cfg["paths"]["window_interim"].mkdir(parents=True, exist_ok=True)
    if len(undated):
        undated.to_parquet(cfg["paths"]["window_interim"] / "raw_undated.parquet", index=False)

    # Partial first/last UTC day (same rule as Phase 1, from the per-day counts).
    s = pd.Series(counts).sort_index()
    partial = []
    if len(s) >= 3:
        for dd in (s.index[0], s.index[-1]):
            if s[dd] < cfg["quality"]["partial_day_min_share"] * s.drop(dd).median():
                partial.append(dd)
    full = [dd for dd in s.index if dd not in partial]
    coverage = {"start_utc": f"{full[0]}T00:00:00+00:00" if full else None,
                "end_utc": (pd.Timestamp(full[-1], tz="UTC") + pd.Timedelta(days=1)).isoformat() if full else None}
    pad = cfg.get("study_bbox_pad_deg", 0.1)
    r = lambda v, fn: float(fn(v * 10) / 10)  # noqa: E731
    detected = [max(r(bounds[0] - pad, np.floor), -180.0), max(r(bounds[1] - pad, np.floor), -90.0),
                min(r(bounds[2] + pad, np.ceil), 180.0), min(r(bounds[3] + pad, np.ceil), 90.0)]
    bbox = list(cfg.get("study_bbox") or detected)
    era_tab = eras_mod.measure(hist, presence, cfg)
    era_tab.to_csv(cfg["paths"]["window_interim"] / "eras.csv", index=False)
    man = {"window": w["name"], "raw_files": [f.name for f in files], "utc_day_counts": counts,
           "n_undated": int(len(undated)), "partial_days": sorted(partial), "coverage": coverage,
           "bbox": bbox, "bbox_source": "config" if cfg.get("study_bbox") else "detected",
           "eras": era_tab.to_dict("records")}
    mpath.write_text(json.dumps(man, indent=2, default=str))
    return load_manifest(cfg)


# ------------------------------------------------------------------ detect ---
def detect_day(cfg: dict, day: date, force: bool = False) -> dict:
    root = cfg["paths"]["partition_root"]
    if P.exists(root, "detections", day) and not force:
        return {"day": str(day), "skipped": True}
    t0 = time.perf_counter()
    man = load_manifest(cfg)
    raw = read_raw_days(root, [day - timedelta(days=1), day, day + timedelta(days=1)])
    empty = raw.empty
    if not empty:
        det = ingest.standardize(raw, cfg)
        det["det_id"] = stable_ids(det["source_file"], det["source_row"])
        det["drifted_era"] = eras_mod.flag_rows(det, man["eras"])
        # Region first: drop rows outside the study bbox before any geometry work.
        x0, y0, x1, y1 = man["bbox"]
        outside = det["latitude"].notna() & ~(det["longitude"].between(x0, x1) & det["latitude"].between(y0, y1))
        n_out = int((outside & (det[DAY_COL] == str(day))).sum())
        det = det[~outside]
        qc = quality.run(det, cfg, bbox=man["bbox"], partial=man["partial_days"], coverage=man["coverage"],
                         quiet=True)
        today = lambda df: df[df[DAY_COL] == str(day)]  # noqa: E731
        clean, low, removed = today(qc["clean"]), today(qc["lowconf"]), today(qc["removed"])
    if empty or clean.empty:
        for st in ("detections", "lowconf", "removed"):
            P.write(pd.DataFrame(), root, st, day)
        P.write(pd.DataFrame([{"day": str(day), "n_clean": 0}]), root, "day_stats", day)
        return {"day": str(day), "n_clean": 0, "seconds": time.perf_counter() - t0}

    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        fp = footprints.run(clean, cfg)
    gdf = fp.set_index("det_id", drop=False)
    links = ev_mod.daily_links(gdf)
    g = nx.Graph()
    g.add_nodes_from(gdf.index)
    g.add_edges_from(links[["i", "j"]].itertuples(index=False, name=None))
    e = cfg["events"]
    pieces, split_rows = [], {}
    n_split_comps, n_split_pieces, split_ext, split_dur = 0, 0, 0, 0
    for comp in nx.connected_components(g):
        members = np.array(sorted(comp))
        if len(members) == 1:
            pieces.append(members)
            continue
        ps, reasons = ev_mod.split_by_caps(members, g, gdf, DAY_COL, e["cap_extent_km"], e["cap_duration_days"])
        if len(ps) > 1:
            n_split_comps += 1
            n_split_pieces += len(ps)
            split_ext += "extent" in reasons
            split_dur += "duration" in reasons
            for p in ps:
                for m in p:
                    split_rows[m] = "+".join(reasons)
        pieces += ps
    order = sorted(pieces, key=lambda p: (gdf.loc[p, "acq_datetime_utc"].min(), int(p.min())))
    gdf["piece_id"] = ""
    for k, p in enumerate(order):
        gdf.loc[p, "piece_id"] = f"{day:%Y%m%d}-{k:06d}"
    gdf["day_split_reason"] = gdf.index.map(lambda i: split_rows.get(i, ""))
    out = pd.DataFrame(gdf.drop(columns="geometry")).reset_index(drop=True)
    out["geometry_wkb"] = shapely.to_wkb(gdf.geometry.to_numpy())
    out = out.sort_values("det_id", kind="stable").reset_index(drop=True)
    P.write(out, root, "detections", day)
    P.write(low.reset_index(drop=True), root, "lowconf", day)
    P.write(removed.reset_index(drop=True), root, "removed", day)
    stats = {"day": str(day), "n_clean": len(clean), "n_lowconf": len(low), "n_removed": len(removed),
             "n_outside_bbox": n_out, "n_daily_links": len(links), "n_links_overlap": int(links["overlap"].sum()),
             "n_links_halfdiag_only": int((~links["overlap"] & links["within_halfdiag"]).sum()),
             "n_day_split_components": n_split_comps, "n_day_split_pieces": n_split_pieces,
             "n_day_split_extent": split_ext, "n_day_split_duration": split_dur,
             "n_urt_duplicates": int(qc["reason_counts"].get("urt_duplicate_of_nrt", 0))}
    P.write(pd.DataFrame([stats]), root, "day_stats", day)
    return {**stats, "seconds": time.perf_counter() - t0}


def _gdf_from_part(df: pd.DataFrame) -> gpd.GeoDataFrame:
    wkb = np.array([bytes(b) for b in df["geometry_wkb"]], dtype=object)  # DuckDB returns bytearray
    return gpd.GeoDataFrame(df.drop(columns="geometry_wkb"), geometry=shapely.from_wkb(wkb), crs="EPSG:4326")


# -------------------------------------------------------------------- link ---
def _hull(geoms) -> shapely.Geometry:
    return shapely.convex_hull(shapely.union_all(np.asarray(geoms, dtype=object)))


def _extent_of(geoms) -> float:
    xy = shapely.get_coordinates(np.asarray(geoms, dtype=object))
    return ev_mod.extent_km(np.asarray(geoms, dtype=object), xy[:, 0], xy[:, 1])


def link_day(cfg: dict, day: date, force: bool = False) -> dict:
    """Assign fire ids for day D using only day D-1 (its detections, assignments and event state)."""
    root = cfg["paths"]["partition_root"]
    if P.exists(root, "assign", day) and not force:
        return {"day": str(day), "skipped": True}
    t0 = time.perf_counter()
    e = cfg["events"]
    cap_km, cap_days = e["cap_extent_km"], e["cap_duration_days"]
    cur = P.read(root, "detections", day)
    if cur is None or cur.empty:
        for st in ("assign", "event_state", "merges", "link_stats"):
            P.write(pd.DataFrame(), root, st, day)
        return {"day": str(day), "n_events_today": 0, "seconds": time.perf_counter() - t0}
    gcur = _gdf_from_part(cur)
    prev_day = day - timedelta(days=1)
    pdet, pas, pstate = (P.read(root, "detections", prev_day, columns=["det_id", "geometry_wkb"]),
                         P.read(root, "assign", prev_day), P.read(root, "event_state", prev_day))
    have_prev = pdet is not None and not pdet.empty and pas is not None and not pas.empty
    piece_geoms = {pid: g.geometry.to_numpy() for pid, g in gcur.groupby("piece_id", sort=True)}
    links: dict[str, set] = {pid: set() for pid in piece_geoms}
    hulls, starts = {}, {}
    n_multi = 0
    if have_prev:
        pg = shapely.from_wkb(pdet["geometry_wkb"].to_numpy())
        fid_of = pas.set_index("det_id")["fire_id"]
        tree = shapely.STRtree(pg)
        ia, ib = tree.query(gcur.geometry.to_numpy(), predicate="intersects")
        n_multi = len(ia)
        prev_fire = fid_of.reindex(pdet["det_id"].to_numpy()[ib]).to_numpy()
        for pid, f in zip(gcur["piece_id"].to_numpy()[ia], prev_fire):
            links[pid].add(f)
        st = pstate.set_index("fire_id")
        hulls = {f: shapely.from_wkb(h) for f, h in st["hull_wkb"].items()}
        starts = {f: pd.Timestamp(s).date() for f, s in st["start_day"].items()}

    assign_rows, merges, state = [], [], {}
    new_k = 0

    def new_id():
        nonlocal new_k
        new_k += 1
        return f"FE{day:%Y%m%d}{new_k:05d}"

    # Components of (today's pieces + yesterday's fires).
    G = nx.Graph()
    for pid, fs in links.items():
        G.add_node(("p", pid))
        for f in fs:
            G.add_edge(("p", pid), ("f", f))
    comps = sorted(nx.connected_components(G), key=lambda c: min(n[1] for n in c if n[0] == "p"))
    for comp in comps:
        pids = sorted(n[1] for n in comp if n[0] == "p")
        fires = sorted(n[1] for n in comp if n[0] == "f")
        target, reason, split_from = None, "", ""
        if fires:
            start = min(starts.get(f, day) for f in fires)
            all_geoms = np.concatenate([np.array([hulls[f] for f in fires if f in hulls], dtype=object)] +
                                       [piece_geoms[p] for p in pids])
            if (day - start).days + 1 > cap_days:
                reason, split_from = "duration", fires[0]
            elif _extent_of(all_geoms) > cap_km:
                reason, split_from = "extent", fires[0]
            else:
                target = fires[0]
                merges += [{"from_id": f, "to_id": target, "day": str(day)} for f in fires[1:]]
        if target is not None:
            hull_geoms = np.concatenate([np.array([hulls[f] for f in fires if f in hulls], dtype=object)] +
                                        [piece_geoms[p] for p in pids])
            state[target] = {"start_day": min(starts.get(f, day) for f in fires), "geoms": hull_geoms}
            for p in pids:
                assign_rows.append((p, target, "", ""))
        else:
            # New event(s): each piece on its own when it could not join (caps), else together.
            for p in pids:
                fid = new_id()
                state[fid] = {"start_day": day, "geoms": piece_geoms[p]}
                assign_rows.append((p, fid, reason, split_from))
    a = pd.DataFrame(assign_rows, columns=["piece_id", "fire_id", "split_reason", "split_from"])
    assign = (cur[["det_id", "piece_id"]].merge(a, on="piece_id", how="left")
              .assign(event_start_day=lambda x: x["fire_id"].map(lambda f: str(state[f]["start_day"]))))
    assign = assign.sort_values("det_id", kind="stable").reset_index(drop=True)
    st_rows = [{"fire_id": f, "start_day": str(v["start_day"]), "hull_wkb": shapely.to_wkb(_hull(v["geoms"]))}
               for f, v in sorted(state.items())]
    P.write(assign, root, "assign", day)
    P.write(pd.DataFrame(st_rows), root, "event_state", day)
    P.write(pd.DataFrame(merges, columns=["from_id", "to_id", "day"]), root, "merges", day)
    a_split = a[a["split_reason"] != ""]
    stats = {"day": str(day), "n_events_today": len(state), "n_merges": len(merges), "n_multiday_links": n_multi,
             "n_link_split_components": int(a_split["split_from"].nunique()),
             "n_link_split_extent": int(a_split.loc[a_split["split_reason"] == "extent", "split_from"].nunique()),
             "n_link_split_duration": int(a_split.loc[a_split["split_reason"] == "duration", "split_from"].nunique())}
    P.write(pd.DataFrame([stats]), root, "link_stats", day)
    return {**stats, "seconds": time.perf_counter() - t0}


# -------------------------------------------------------------------- grid ---
def grid_day(cfg: dict, day: date, force: bool = False) -> dict:
    root = cfg["paths"]["partition_root"]
    if P.exists(root, "grid_overpass", day) and not force:
        return {"day": str(day), "skipped": True}
    t0 = time.perf_counter()
    cur, asg = P.read(root, "detections", day), P.read(root, "assign", day)
    if cur is None or cur.empty:
        P.write(pd.DataFrame(), root, "grid_overpass", day)
        P.write(pd.DataFrame(), root, "grid_cellday", day)
        return {"day": str(day), "seconds": time.perf_counter() - t0}
    man = load_manifest(cfg)
    c = {**cfg, "_coverage": man["coverage"]}
    g = _gdf_from_part(cur).merge(asg[["det_id", "fire_id"]], on="det_id")
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        r = grid.run(g, c)
    P.write(r["overpass"].sort_values(["cell_id", "acq_datetime_utc", "platform"]).reset_index(drop=True),
            root, "grid_overpass", day)
    P.write(r["daily"].sort_values("cell_id").reset_index(drop=True), root, "grid_cellday", day)
    return {"day": str(day), "frp_before": r["energy"]["frp_before_mw"], "frp_after": r["energy"]["frp_after_mw"],
            "seconds": time.perf_counter() - t0}


# ---------------------------------------------------------------- finalize ---
def resolve_merges(merges: pd.DataFrame) -> dict:
    """Union-find over merge rows -> canonical (earliest) id for every merged id."""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x
    for a, b in merges[["from_id", "to_id"]].itertuples(index=False) if len(merges) else []:
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            parent[hi] = lo
    return {k: find(k) for k in list(parent)}


class Count:
    """Stands in for a table whose only use downstream is len()."""
    def __init__(self, n):
        self.n = int(n)

    def __len__(self):
        return self.n


def finalize(cfg: dict, write_outputs: bool = True) -> dict:
    """Resolve merges and build the window tables. Events are finalised in chunks of
    `finalize_chunk_days` by start day; each chunk reads its days plus cap_duration_days."""
    import duckdb
    root, w = cfg["paths"]["partition_root"], cfg["window"]
    d0, d1 = local_days(cfg)[0], local_days(cfg)[-1]
    wp, wi = cfg["paths"]["window_processed"], cfg["paths"]["window_interim"]
    wp.mkdir(parents=True, exist_ok=True)
    wi.mkdir(parents=True, exist_ok=True)
    e = cfg["events"]
    con = P.connect()
    merges = P.duck(root, "merges", d0, d1, con=con)
    canon = resolve_merges(merges)
    asg = P.duck(root, "assign", d0, d1, con=con)
    asg["final_id"] = asg["fire_id"].map(lambda f: canon.get(f, f))
    start = asg.groupby("final_id")["event_start_day"].min()
    asg["event_start_day"] = asg["final_id"].map(start)

    chunk = cfg["partitions"]["finalize_chunk_days"]
    ev_parts, ov_parts, det_parts, fp_parts = [], [], [], []
    cs = d0
    while cs <= d1:
        ce = min(cs + timedelta(days=chunk - 1), d1)
        ids = asg.loc[(pd.to_datetime(asg["event_start_day"]).dt.date >= cs) &
                      (pd.to_datetime(asg["event_start_day"]).dt.date <= ce)]
        if len(ids):
            files = P.glob_for(root, "detections", cs, min(ce + timedelta(days=e["cap_duration_days"]), d1))
            con.register("ids", ids[["det_id", "final_id", "split_reason", "split_from"]])
            d = con.execute(f"SELECT t.*, ids.final_id, ids.split_reason AS link_split_reason, "
                            f"ids.split_from AS link_split_from FROM read_parquet({files!r}, union_by_name=true) t "
                            f"JOIN ids USING (det_id)").df()
            g = _gdf_from_part(d)
            g["fire_id"] = g["final_id"]
            # Split bookkeeping (in-day cap splits and link-time cap splits).
            g["split_reason"] = np.where(g["link_split_reason"].fillna("") != "", g["link_split_reason"].fillna(""),
                                         g["day_split_reason"].fillna(""))
            ev_split = g.groupby("fire_id")["split_reason"].agg(lambda s: next((x for x in s if x), ""))
            ev_from = g.groupby("fire_id")["link_split_from"].agg(lambda s: next((x for x in s.fillna("") if x), ""))
            g["split_reason"] = g["fire_id"].map(ev_split)
            g["was_split"] = g["split_reason"] != ""
            g["raw_event"] = g["fire_id"].map(ev_from).where(g["fire_id"].map(ev_from) != "",
                                                              "day:" + g["piece_id"].astype(str))
            codes = pd.factorize(g["fire_id"])[0]
            g["extent_km"] = ev_mod.piece_extents(g, codes)
            events, ov = ev_mod.build_tables(g, cfg, DAY_COL)
            ev_parts.append(events)
            ov_parts.append(ov)
            det_parts.append(pd.DataFrame(g.drop(columns=["geometry", "final_id", "link_split_reason",
                                                          "link_split_from"])))
            fp_parts.append(g[["det_id", "fire_id", "sensor", "platform", "acq_datetime_utc", "scan_km", "track_km",
                               "track_heading_deg", "footprint_area_km2", "frp_mw", "p_conf", "geometry"]])
        cs = ce + timedelta(days=1)
    events = pd.concat(ev_parts, ignore_index=True).sort_values(["start_time", "fire_id"]).reset_index(drop=True)
    ov = pd.concat(ov_parts, ignore_index=True)
    det = pd.concat(det_parts, ignore_index=True).sort_values("det_id").reset_index(drop=True)
    pairs = ev_mod.matched_pairs(ov, cfg)
    gov = P.duck(root, "grid_overpass", d0, d1, con=con)
    gcd = P.duck(root, "grid_cellday", d0, d1, con=con)
    low = P.duck(root, "lowconf", d0, d1, "SELECT count(*) AS n FROM t", con=con)
    rem = P.duck(root, "removed", d0, d1, con=con)
    und = wi / "raw_undated.parquet"
    if und.exists():  # rows without a usable date: removed with their reason codes
        u = pd.read_parquet(und)
        if len(u):
            q = quality.run(ingest.standardize(u, cfg).assign(det_id=lambda x: stable_ids(x["source_file"], x["source_row"])),
                            cfg, bbox=load_manifest(cfg)["bbox"], partial=[], coverage={}, quiet=True)
            rem = pd.concat([rem, q["removed"]], ignore_index=True)
    ds = P.duck(root, "day_stats", d0, d1, con=con)
    con.close()
    out = {"events": events, "overpasses": ov, "pairs": pairs, "detections": det, "grid_overpass": gov,
           "grid_daily": gcd, "n_lowconf": int(low["n"].iloc[0]) if len(low) else 0, "removed": rem,
           "day_stats": ds, "canon": canon, "footprints": pd.concat(fp_parts, ignore_index=True)}
    if write_outputs:
        stamp = {"data_version": cfg["data_version"], "processing_date": cfg["processing_date"]}
        det.assign(**stamp).to_parquet(wp / "detections_clean.parquet", index=False)
        events.to_csv(wp / "fire_events.csv", index=False)
        gcd.to_csv(wp / "grid_daily.csv", index=False)
        ov.assign(**stamp).to_csv(wi / "event_overpasses.csv", index=False)
        pairs.to_csv(wi / "matched_pairs_aqua_viirs.csv", index=False)
        gov.to_csv(wi / "grid_overpass.csv", index=False)
        gpd.GeoDataFrame(out["footprints"], geometry="geometry", crs="EPSG:4326").assign(**stamp) \
            .to_parquet(wi / "footprints.geoparquet", index=False)
        lowd = P.duck(root, "lowconf", d0, d1)
        lowd.assign(**stamp).to_parquet(wi / "detections_lowconf.parquet", index=False)
        rem.assign(**stamp).to_parquet(wi / "detections_removed.parquet", index=False)
    return out
