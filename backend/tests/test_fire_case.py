from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import fire_case
from fire_case import Ballot, build_fire_case, classify_passes


T0 = datetime(2026, 3, 10, 7, 40, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=30)


def _det(hours=0.0, lat=23.85, lon=90.38, sensor="viirs_snpp", frp=8.0, daynight="D", conf=90.0):
    return {"lat": lat, "lon": lon, "acq_datetime": T0 + timedelta(hours=hours), "sensor": sensor, "satellite": "N", "frp": frp, "confidence_pct": conf, "daynight": daynight}


def _pass(witness, hours, in_swath=True, position="mid swath", hour=13.5):
    return {"witness": witness, "label": witness, "time": T0 + timedelta(hours=hours), "off_nadir_km": 500.0, "in_swath": in_swath, "coverage_probability": 1.0, "swath_position": position, "local_solar_hour": hour, "method": "test"}


def test_scores_sum_to_100_and_follow_votes():
    b = Ballot()
    b.add("C", "news", "farm fire", 1.0, {"agricultural_burn": 5.0})
    scores = b.scores()
    assert sum(s["score"] for s in scores) == 100
    assert scores[0]["category"] == "agricultural_burn"


def test_passes_are_classified_seen_clear_cloudy_and_uncovered():
    passes = [_pass("snpp", 0), _pass("noaa20", 12, hour=1.5), _pass("aqua", 24), _pass("terra", 26, in_swath=False), _pass("noaa20", 40)]
    hourly = [{"time": (T0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00"), "cloud_cover": 90 if h == 24 else 10} for h in range(0, 48)]
    out = classify_passes(passes, [_det()], hourly, (23.85, 90.38), 1.0, NOW)
    assert [p["outcome"] for p in out] == ["first_detection", "clear_no_fire", "cloud_or_smoke", "not_covered", "expected"]


def _stub(monkeypatch, passes, season, hourly=None):
    async def fake_passes(lat, lon, t0, t1, on=None):
        return {"passes": passes, "witnesses": ["snpp", "noaa20", "aqua"], "method": "test", "errors": []}

    async def fake_hourly(lat, lon, start, end):
        return hourly or []

    async def fake_season(lat, lon, when):
        return season

    monkeypatch.setattr(fire_case, "predict_passes", fake_passes)
    monkeypatch.setattr(fire_case, "hourly_weather", fake_hourly)
    monkeypatch.setattr(fire_case, "burning_season", fake_season)


EMPTY_REGIONAL = {"checks": [], "corroborating_sources": [], "geostationary_or_highres_match": False, "other_platform_match": False}
EMPTY_OFFICIAL = {"matches": [], "checks": [], "has_official_match": False, "controlled_burn_reported": False}
EMPTY_NEWS = {"articles": [], "searched": {}}


def test_cropland_in_season_short_burn_reads_as_agricultural(monkeypatch):
    season = {"status": "ok", "years_checked": 5, "years_with_fire_within_5km": 5, "years_with_heat_within_1km": 1, "detections_by_year": {}}
    passes = [_pass("snpp", 0), _pass("noaa20", 11, hour=1.0), _pass("aqua", 25)]
    _stub(monkeypatch, passes, season)
    place = {"land_context": {"land_use": ["farmland"], "forests": [], "protected_areas": [], "nearby_heat_sources": []}}
    news = {"articles": [{"relevance_score": 80, "event_type": "AGRICULTURAL_BURN", "source_reliability_score": 70, "published_at": (T0 + timedelta(hours=5)).isoformat(), "publication": "Daily Star", "domain": "thedailystar.net", "match_label": "Strong match", "headline": "Farmers burn paddy stubble", "url": "https://example.org"}], "searched": {}}
    subject = {"lat": 23.85, "lon": 90.38, "detections": [_det()], "radius_km": 0.5, "behaviour": {"state": "Onset"}}
    case = asyncio.run(build_fire_case(subject, place, EMPTY_REGIONAL, EMPTY_OFFICIAL, news, {"final_status": "No External Corroboration Yet"}, now=NOW))
    assert case["answer"]["kind"]["category"] == "agricultural_burn"
    assert case["decision_rules"]["passed"]
    assert case["answer"]["now"]["label"] == "Ended"
    assert case["status"] == "closed"
    assert sum(s["score"] for s in case["category_scores"]) == 100
    assert [i["time"] for i in case["evidence_block"] if i["kind"] != "background" and i["time"]] == sorted(i["time"] for i in case["evidence_block"] if i["kind"] != "background" and i["time"])


def test_repeat_heat_on_the_same_spot_reads_as_industrial(monkeypatch):
    season = {"status": "ok", "years_checked": 5, "years_with_fire_within_5km": 5, "years_with_heat_within_1km": 5, "detections_by_year": {}}
    _stub(monkeypatch, [_pass("snpp", 0, hour=1.5), _pass("snpp", 24, hour=1.5)], season)
    dets = [_det(0, daynight="N"), _det(24, lat=23.8505, daynight="N")]
    place = {"land_context": {"land_use": ["industrial"], "forests": [], "protected_areas": [], "nearby_heat_sources": [{"type": "gas_flare", "name": "Flare", "distance_km": 0.4}]}}
    subject = {"lat": 23.85, "lon": 90.38, "detections": dets, "radius_km": 0.5, "behaviour": {"state": "Persistent"}}
    case = asyncio.run(build_fire_case(subject, place, EMPTY_REGIONAL, EMPTY_OFFICIAL, EMPTY_NEWS, {"final_status": "Likely Non-Fire Thermal Source"}, now=NOW))
    assert case["answer"]["kind"]["category"] == "industrial_source"
    assert case["answer"]["is_real"]["label"] == "Likely non-fire thermal anomaly"


def test_mixed_evidence_does_not_name_a_type_and_stays_provisional(monkeypatch):
    season = {"status": "unavailable"}
    future = _pass("noaa20", 40)
    _stub(monkeypatch, [_pass("snpp", 0), future], season)
    subject = {"lat": 23.85, "lon": 90.38, "detections": [_det()], "radius_km": 0.5, "behaviour": {"state": "Onset"}}
    case = asyncio.run(build_fire_case(subject, {"land_context": {}}, EMPTY_REGIONAL, EMPTY_OFFICIAL, EMPTY_NEWS, {"final_status": "No External Corroboration Yet"}, now=T0 + timedelta(hours=2)))
    assert not case["decision_rules"]["passed"]
    assert case["answer"]["kind"]["category"] == "unknown"
    assert case["provisional"] and case["status"] == "open"
    assert case["marker"]["provisional"]


def test_pending_streams_are_not_treated_as_missing_evidence(monkeypatch):
    _stub(monkeypatch, [_pass("snpp", 0)], {"status": "unavailable"})
    subject = {"lat": 23.85, "lon": 90.38, "detections": [_det()], "radius_km": 0.5, "behaviour": {"state": "Onset"}}
    case = asyncio.run(build_fire_case(subject, {"land_context": {}}, EMPTY_REGIONAL, EMPTY_OFFICIAL, EMPTY_NEWS, {"final_status": "No External Corroboration Yet"}, now=T0 + timedelta(hours=1), pending_streams=["B", "C"]))
    assert case["streams"]["pending"] == ["B", "C"]
    assert case["geostationary"]["status"] == "pending"
    assert not any("No matching report" in i["summary"] for i in case["evidence_block"])


def test_evidence_publishes_a_new_answer_after_each_stream(monkeypatch):
    import evidence

    async def slow(value, delay):
        await asyncio.sleep(delay)
        return value

    monkeypatch.setattr(evidence, "regional_satellite_evidence", lambda s, p: slow(EMPTY_REGIONAL, 0.05))
    monkeypatch.setattr(evidence, "official_evidence", lambda s, p: slow(EMPTY_OFFICIAL, 0.2))
    monkeypatch.setattr(evidence, "news_evidence", lambda s, p: slow(EMPTY_NEWS, 0.4))

    async def fake_case(*args, pending_streams=None, **kwargs):
        return {"streams": {"pending": pending_streams or []}}

    monkeypatch.setattr(evidence, "build_fire_case", fake_case)
    seen = []

    async def on_partial(case):
        seen.append(case["streams"]["pending"])

    subject = {"kind": "hotspot", "lat": 23.85, "lon": 90.38, "detections": [_det()], "t_start": T0, "t_end": T0, "radius_km": 0.5, "sensors": ["viirs_snpp"]}
    asyncio.run(evidence._gather_streams(subject, {}, on_partial))
    assert seen == [["B", "C"], ["C"], ["C"]]
