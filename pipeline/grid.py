"""Step 5: spread footprints over a common 0.1 deg grid.

Each footprint is split across the cells it overlaps with weights
w_ic = Area(F_i ∩ C_c) / Area(F_i), areas in EPSG:6933. Assignment is by
overlap, never by centroid.

FRP is extensive: FRP_c = sum_i w_ic * FRP_i, computed per overpass
(data/interim/grid_overpass.csv). The daily table (grid_daily.csv) takes the
maximum and mean across overpasses, never the sum, because FRP is
instantaneous power.

Energy conservation: total FRP of the detections must equal the total of
FRP_c over all cell-overpass rows. Both numbers are printed on every run.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from pipeline.footprints import area_km2_6933


def cell_index(lon: np.ndarray, lat: np.ndarray, deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Integer column/row of the cell holding each point. Columns wrap at the antimeridian."""
    n_cols = int(round(360 / deg))
    ix = np.floor((np.asarray(lon) + 180.0) / deg + 1e-9).astype(int) % n_cols
    iy = np.floor((np.asarray(lat) + 90.0) / deg + 1e-9).astype(int)
    return ix, iy


def cell_id(ix, iy) -> np.ndarray:
    return np.char.add(np.char.add("r", np.char.zfill(np.asarray(iy).astype(str), 4)),
                       np.char.add("c", np.char.zfill(np.asarray(ix).astype(str), 4)))


def cell_area_km2(iy: np.ndarray, deg: float) -> np.ndarray:
    """True area of a deg x deg cell (EPSG:6933, exact for a lon/lat box)."""
    lat0 = -90 + iy * deg
    box = shapely.box(-deg / 2, lat0, deg / 2, lat0 + deg)
    return area_km2_6933(box, np.zeros(len(np.atleast_1d(iy))))


def overlay(geoms: np.ndarray, deg: float) -> pd.DataFrame:
    """All (footprint, cell) pieces with their equal-area overlap weight.

    Footprint longitudes may run past +/-180 near the antimeridian; cells are
    built in the same unwrapped frame and their column index is wrapped after.
    """
    b = shapely.bounds(geoms)
    x0 = np.floor(b[:, 0] / deg + 1e-9).astype(int)
    x1 = np.floor(b[:, 2] / deg - 1e-9).astype(int)
    y0 = np.floor(b[:, 1] / deg + 1e-9).astype(int)
    y1 = np.floor(b[:, 3] / deg - 1e-9).astype(int)
    nx_, ny_ = x1 - x0 + 1, y1 - y0 + 1
    n = nx_ * ny_
    fid = np.repeat(np.arange(len(geoms)), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    cx = np.repeat(x0, n) + k % np.repeat(nx_, n)
    cy = np.repeat(y0, n) + k // np.repeat(nx_, n)
    boxes = shapely.box(cx * deg, cy * deg, (cx + 1) * deg, (cy + 1) * deg)
    pieces = shapely.intersection(geoms[fid], boxes)
    ref_lon = (cx + 0.5) * deg
    area = area_km2_6933(pieces, ref_lon)
    full = area_km2_6933(geoms, shapely.get_x(shapely.centroid(geoms)))
    out = pd.DataFrame({"row": fid, "piece_area_km2": area, "fp_area_km2": full[fid],
                        "ix": (cx + int(round(180 / deg))) % int(round(360 / deg)),
                        "iy": cy + int(round(90 / deg))})
    out = out[out["piece_area_km2"] > 0]
    out["w_raw"] = out["piece_area_km2"] / out["fp_area_km2"]
    # Pieces partition the footprint, so the raw weights sum to 1 up to float
    # error. Normalise so energy is conserved exactly; the raw deviation is reported.
    out["w"] = out["w_raw"] / out.groupby("row")["w_raw"].transform("sum")
    return out


def run(det: gpd.GeoDataFrame, cfg: dict) -> dict:
    deg = cfg["grid"]["cell_deg"]
    day_col = "local_solar_date" if cfg["events"].get("day_basis") == "local_solar" else "utc_date"
    det = det.reset_index(drop=True)
    pieces = overlay(det.geometry.to_numpy(), deg)
    weight_dev = float(pieces.groupby("row")["w_raw"].sum().sub(1).abs().max())

    cols = ["det_id", "fire_id", "sensor", "platform", "acq_datetime_utc", day_col,
            "frp_mw", "bt_k", "p_conf", "footprint_area_km2"]
    p = pieces.join(det[cols], on="row")
    p["cell_id"] = cell_id(p["ix"].to_numpy(), p["iy"].to_numpy())
    p["frp_w"] = p["w"] * p["frp_mw"]
    p["date"] = p[day_col]

    # ---- per cell and overpass (FRP is additive here) ----
    gov = (p.groupby(["cell_id", "date", "sensor", "platform", "acq_datetime_utc"])
             .agg(frp_mw=("frp_w", "sum"), n_detections_weighted=("w", "sum"),
                  n_footprints=("det_id", "nunique"), bt_max_k=("bt_k", "max"),
                  p_conf_max=("p_conf", "max"))
             .reset_index())

    # ---- event counts weighted by overlap share of the event's footprint union that day ----
    keys, unions = [], []
    for (fid, date), g in det.groupby(["fire_id", day_col], sort=False):
        geoms = g.geometry.to_numpy()
        keys.append((fid, date))
        unions.append(geoms[0] if len(geoms) == 1 else shapely.union_all(geoms))
    ov = overlay(np.array(unions, dtype=object), deg)
    k = pd.DataFrame(keys, columns=["fire_id", "date"])
    ev = pd.DataFrame({"cell_id": cell_id(ov["ix"].to_numpy(), ov["iy"].to_numpy()),
                       "fire_id": k["fire_id"].to_numpy()[ov["row"]],
                       "date": k["date"].to_numpy()[ov["row"]], "w": ov["w"].to_numpy()})
    ev_cell = ev.groupby(["cell_id", "date"]).agg(n_events_weighted=("w", "sum"),
                                                  n_events_touching=("fire_id", "nunique"))

    # ---- per cell and day: max/mean across overpasses, never a sum of FRP ----
    def by_sensor(s):
        sub = gov[gov["sensor"] == s].groupby(["cell_id", "date"])["frp_mw"]
        return sub.max().rename(f"frp_{s}_max_overpass_mw")

    daily = (gov.groupby(["cell_id", "date"])
                .agg(n_overpasses=("acq_datetime_utc", "nunique"),
                     platforms_seen=("platform", lambda s: ";".join(sorted(set(s)))),
                     sensors=("sensor", lambda s: ";".join(sorted(set(s)))),
                     frp_max_overpass_mw=("frp_mw", "max"),
                     frp_mean_overpass_mw=("frp_mw", "mean"),
                     n_detections_weighted=("n_detections_weighted", "sum"),
                     bt_max_k=("bt_max_k", "max"),
                     p_conf_max=("p_conf_max", "max")))
    daily = daily.join(by_sensor("MODIS")).join(by_sensor("VIIRS")).join(ev_cell).reset_index()
    daily["sensor_flag"] = daily["sensors"].map({"MODIS": "MODIS_only", "VIIRS": "VIIRS_only",
                                                 "MODIS;VIIRS": "both"})
    iy = daily["cell_id"].str[1:5].astype(int).to_numpy()
    ix = daily["cell_id"].str[6:10].astype(int).to_numpy()
    daily.insert(2, "cell_lat", np.round(-90 + (iy + 0.5) * deg, 4))
    daily.insert(3, "cell_lon", np.round(-180 + (ix + 0.5) * deg, 4))
    daily.insert(4, "cell_area_km2", cell_area_km2(iy, deg))
    daily["frp_density_max_mw_km2"] = daily["frp_max_overpass_mw"] / daily["cell_area_km2"]
    # Partial day: the cell's local solar day is not fully inside the UTC interval the
    # data covers completely (download cut-off at either end). Excluded from daily statistics.
    cov = cfg.get("_coverage") or {}
    if cov.get("start_utc") is not None:
        start = (pd.to_datetime(daily["date"]).dt.tz_localize("UTC")
                 - pd.to_timedelta(daily["cell_lon"] / 15.0, unit="h"))
        daily["partial_day"] = (start < cov["start_utc"]) | (start + pd.Timedelta(days=1) > cov["end_utc"])
    else:
        daily["partial_day"] = False
    daily["data_version"] = cfg["data_version"]
    daily["processing_date"] = cfg["processing_date"]
    gov["data_version"] = cfg["data_version"]

    before = float(det["frp_mw"].sum())
    after = float(gov["frp_mw"].sum())
    rel = abs(after - before) / before if before else 0.0
    ok = rel <= cfg["grid"]["energy_rel_tol"]
    print(f"[Step 5] Energy conservation: FRP before gridding = {before:.6f} MW, "
          f"after = {after:.6f} MW, rel. diff = {rel:.2e} -> {'PASS' if ok else 'FAIL'}")
    print(f"         {len(daily)} cell-days, {len(gov)} cell-overpass rows; "
          f"max raw weight-sum deviation {weight_dev:.2e}")
    return {"daily": daily, "overpass": gov, "pieces": p,
            "energy": {"frp_before_mw": before, "frp_after_mw": after, "rel_diff": rel, "pass": ok,
                       "max_weight_sum_deviation": weight_dev}}
