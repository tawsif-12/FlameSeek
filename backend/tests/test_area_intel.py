from datetime import date, datetime, timedelta

import numpy as np

from area_intel import area_climatology, hotspot_recurrence


def _row(lat, lon, day, conf=80):
    return {"lat": lat, "lon": lon, "acq_datetime": datetime.combine(day, datetime.min.time()), "confidence_pct": conf}


def test_recurrence_counts_distinct_days_years_and_drops_low_confidence():
    d1, d2 = date(2020, 3, 1), date(2021, 3, 5)
    rows = [_row(22.01, 89.01, d1), _row(22.01, 89.01, d1), _row(22.01, 89.01, d2), _row(22.01, 89.01, d2, conf=10),
            _row(22.5, 89.5, d1)]
    out = hotspot_recurrence(rows, (88.9, 21.9, 89.9, 22.9))
    top = out["cells"][0]
    assert top["detections"] == 3 and top["days"] == 2 and top["years"] == 2
    assert out["n_cells_with_fire"] == 2 and out["detections_used"] == 4


def _daily(start, end, fire_fn):
    days, d = [], start
    while d <= end:
        days.append({"date": d.isoformat(), "harmonized_activity": 1.0 if fire_fn(d) else 0.0})
        d += timedelta(days=1)
    return days


def test_climatology_withheld_with_short_history():
    daily = _daily(date(2023, 1, 1), date(2025, 12, 31), lambda d: d.month == 3)
    assert area_climatology(daily, date(2025, 12, 31))["status"] == "insufficient_history"


def test_seasonal_record_gives_high_in_season_probability_and_positive_skill():
    daily = _daily(date(2014, 1, 1), date(2025, 2, 27), lambda d: d.month == 3)  # fires every March
    out = area_climatology(daily, date(2025, 2, 27))
    assert out["status"] == "computed" and out["probability"] > 0.7
    assert out["validation"]["brier_skill_score"] > 0.3
    off = area_climatology(daily[:-200], date.fromisoformat(daily[-201]["date"]))  # window in late summer
    assert off["probability"] < 0.3


def test_random_record_shows_no_skill():
    rng = np.random.default_rng(1)
    flags = {}
    daily = _daily(date(2014, 1, 1), date(2025, 6, 30), lambda d: flags.setdefault(d, rng.random() < 0.01))
    out = area_climatology(daily, date(2025, 6, 30))
    assert out["status"] == "computed" and out["validation"]["brier_skill_score"] <= 0.05
