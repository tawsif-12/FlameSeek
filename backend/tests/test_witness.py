from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from harmonize import build_harmonized_series
from witness import (
    DEFAULT_DIURNAL,
    PRIOR_PROFILE,
    REFERENCE_HOUR,
    clean_and_tag,
    continuity_test,
    detection_probability,
    looks_per_pass,
    merge_overpass,
    time_factor,
    witness_of,
)


T = datetime(2024, 3, 1, 7, 30, tzinfo=timezone.utc)


def _row(sensor="modis", satellite="Aqua", lat=23.5, lon=90.0, t=T, frp=10.0, conf=80.0, **extra):
    return {"lat": lat, "lon": lon, "acq_datetime": t, "confidence_pct": conf, "frp": frp, "sensor": sensor, "satellite": satellite, "scan_km": 1.0, "track_km": 1.0, **extra}


def test_witness_identification_and_local_solar_time():
    assert witness_of(_row(satellite="Terra")) == "terra"
    assert witness_of(_row(sensor="viirs_noaa20", satellite="1")) == "noaa20"
    # 07:30 UTC at 90E is 13:30 local solar time: an Aqua-like pass.
    assert witness_of(_row(satellite="")) == "aqua"
    tagged, _ = clean_and_tag([_row()])
    assert abs(tagged[0]["local_solar_hour"] - 13.5) < 0.01
    assert tagged[0]["cell"] == (235, 900)


def test_clean_drops_non_vegetation_and_low_confidence():
    tagged, dropped = clean_and_tag([_row(fire_type=2), _row(conf=20), _row(fire_type=0), _row(sensor="goes")])
    assert len(tagged) == 1
    assert dropped == {"low_confidence": 1, "non_vegetation_type": 1, "not_a_witness": 1}


def test_modis_duplicates_merge_keeping_higher_frp_but_viirs_clusters_sum():
    rows, _ = clean_and_tag([_row(frp=5), _row(lat=23.5045, frp=12), _row(lat=23.6, frp=3)])
    merged = merge_overpass(rows, 1.0, "max")
    assert len(merged) == 2
    assert max(r["frp"] for r in merged) == 12
    viirs, _ = clean_and_tag([_row(sensor="viirs_snpp", satellite="N", frp=2), _row(sensor="viirs_snpp", satellite="N", lat=23.503, frp=3)])
    assert merge_overpass(viirs, 1.0, "sum")[0]["frp"] == 5


def test_prior_profile_matches_published_modis_thresholds():
    assert abs(detection_probability(PRIOR_PROFILE, 4.3, 0.375 * 0.375) - 0.5) < 0.01
    edge = 0.375 * 0.375 * 4.4
    assert abs(detection_probability(PRIOR_PROFILE, 31.7, edge) - 0.5) < 0.05
    assert detection_probability(PRIOR_PROFILE, 50, 0.14) > detection_probability(PRIOR_PROFILE, 2, 0.14)


def test_time_factor_is_one_at_reference_and_boosts_morning_passes():
    assert abs(time_factor(DEFAULT_DIURNAL, REFERENCE_HOUR) - 1) < 1e-9
    assert time_factor(DEFAULT_DIURNAL, 10.5) > 1.5


def test_effort_shows_equator_gaps_for_modis_and_polar_oversampling():
    assert looks_per_pass("aqua", 0) < 1 < looks_per_pass("snpp", 0)
    assert looks_per_pass("aqua", 70) > 2


def _synthetic(seed=1):
    rnd = random.Random(seed)
    rows = []
    start, end = date(2010, 1, 1), date(2014, 6, 30)
    d = start
    while d <= end:
        for _ in range(rnd.randint(0, 5) if d.month in (2, 3, 4) else rnd.randint(0, 1)):
            lat, lon = 23 + rnd.random(), 90 + rnd.random()
            frp = rnd.lognormvariate(1.5, 1.2)
            base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            seen = 0.15 + min(0.85, frp / 30)
            if rnd.random() < seen:
                rows.append(_row(lat=lat, lon=lon, t=base + timedelta(hours=7.5), frp=frp))
            if rnd.random() < seen * 0.6:
                rows.append(_row(satellite="Terra", lat=lat, lon=lon, t=base + timedelta(hours=4.5), frp=frp))
            if d >= date(2012, 1, 20):
                for k in range(rnd.randint(1, 3)):
                    rows.append(_row(sensor="viirs_snpp", satellite="N", lat=lat + 0.003 * k, lon=lon, t=base + timedelta(hours=7.6), frp=frp / 2, conf=90))
        d += timedelta(days=1)
    avail = {start + timedelta(days=i): (["modis", "viirs_snpp"] if start + timedelta(days=i) >= date(2012, 1, 20) else ["modis"]) for i in range((end - start).days + 1)}
    return rows, start, end, avail


def test_consistent_record_removes_the_2012_viirs_step_and_hidden_witness_is_predicted():
    rows, start, end, avail = _synthetic()
    daily, cal = build_harmonized_series(rows, start, end, ["modis", "viirs_snpp"], avail, None, area_km2=12000, lat_center=23.5, validate=True)
    step = continuity_test(daily)[0]
    assert step["raw_count_ratio"] > 2.5
    assert abs(step["consistent_record_ratio"] - 1) < 0.35
    assert step["verdict"] == "step removed"
    hidden = cal["witness"]["validation"]["hide_one_witness"]
    assert hidden["status"] == "ok"
    assert hidden["auc_fused"] > hidden["auc_prior_only"] > 0.5
    assert cal["witness"]["summary"]["detection_profile"]["source"] == "learned"
    assert all(r["harmonized_low"] <= r["harmonized_activity"] <= r["harmonized_high"] for r in daily)
    assert all(0 <= r["fire_probability"] <= 1 for r in cal["witness"]["cell_days_recent"])
