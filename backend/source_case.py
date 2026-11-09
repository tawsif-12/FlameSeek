"""Fire case presentation from recorded observations and linked source reports.

Absence in a hotspot feed is not an observation of absence. Unvalidated
category scores, fire probabilities and extinction claims are withheld.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any


async def build_fire_case(subject, place, regional, official, news, fusion,
                          now=None, pending_streams=None, overrides=None) -> dict[str, Any]:
    from fire_case import (CASE_WINDOW_HOURS, NEWS_CATEGORY, CATEGORY_LABEL,
                           WITNESS_LABEL, _utc, _iso, classify_passes,
                           geostationary_stream, predict_passes)

    pending_streams = pending_streams or []
    now = now or datetime.now(timezone.utc)
    dets = sorted(subject['detections'], key=lambda d: _utc(d['acq_datetime']))
    first, last = _utc(dets[0]['acq_datetime']), _utc(dets[-1]['acq_datetime'])
    closes = first + timedelta(hours=CASE_WINDOW_HOURS)
    lat, lon = subject['lat'], subject['lon']
    if overrides is not None and 'overpasses' in overrides:
        orbits = overrides['overpasses']
    else:
        try:
            orbits = await asyncio.wait_for(predict_passes(
                lat, lon, first - timedelta(minutes=30), max(closes, now + timedelta(hours=12)), first.date()), 12)
        except asyncio.TimeoutError:
            from witness import WITNESSES, WITNESS_START
            orbits = dict(passes=[], witnesses=[w for w in WITNESSES if first.date() >= WITNESS_START[w]],
                          method='orbital predictions unavailable', errors=['Orbital source lookup timed out; no nominal schedule substituted.'])
        if overrides is not None:
            overrides['overpasses'] = orbits
    passes = classify_passes(orbits['passes'], dets, [], (lat, lon), subject.get('radius_km', 1), now)
    observed = [p for p in passes if p.get('detections')]
    future = [p for p in passes if p['outcome'] == 'expected' and p['in_swath']]
    items = []

    def add(stream, source, summary, when=None, link=None, kind='observation'):
        items.append(dict(stream=stream, source=source, summary=summary,
                          time=_iso(when), link=link, kind=kind, votes={}, reliability=1.0))

    for i, p in enumerate(observed):
        add('trigger' if i == 0 else 'A', p['label'],
            f"Recorded satellite heat: {p['detections']} detection(s), summed pass FRP {p['frp_mw']:.1f} MW. Sensor confidence is not a wildfire probability.",
            p['time'], 'https://firms.modaps.eosdis.nasa.gov/map/')
    geo = geostationary_stream(regional) if 'B' not in pending_streams else dict(
        status='pending', detail='Regional satellite check pending.', review_links=[])
    add('B', geo.get('satellite') or 'Regional satellite', geo.get('detail') or 'Regional satellite observations returned.', now, kind='note')
    for check in regional.get('checks', []):
        if check.get('status') == 'corroborating':
            add('B', check['name'], check.get('detail') or 'Matching source observations returned.',
                now, check.get('review_url'), 'external')

    # Require original source links before presenting a report as evidence.
    reports = [m for m in official.get('matches', []) if m.get('url')]
    articles = [a for a in news.get('articles', []) if a.get('url') and a.get('relevance_score', 0) >= 55]
    for m in reports:
        add('C', m.get('source') or 'Official source',
            f"Matched official report: {m.get('title') or 'Incident'}; reported type: {m.get('incident_type') or 'unspecified'}. Event association is a geographic/time matching inference.",
            _utc(m['discovered']) if m.get('discovered') else None, m['url'], 'external')
    for a in articles:
        add('C', a.get('publication') or a.get('domain') or 'News source',
            f"Potentially matching article: {a['headline']}. Relevance and event association are system estimates, not official confirmation.",
            _utc(a['published_at']) if a.get('published_at') else None, a['url'], 'external')
    checks = official.get('checks', [])
    searched = news.get('searched', {})
    news_failed = bool(searched.get('gdelt_error'))
    unavailable = [c.get('name', 'Official feed') for c in checks if c.get('status') in
                   {'unavailable', 'not_connected', 'manual_review', 'review_available'}]
    official_checked = any(c.get('status') in {'match', 'no_match'} for c in checks)
    news_checked = bool(searched.get('gdelt_url')) and not news_failed
    complete_search = official_checked and news_checked and not unavailable
    report_status = 'pending' if 'C' in pending_streams else 'done' if complete_search else 'partial'
    if 'C' not in pending_streams and not reports and not articles:
        add('C', 'News and official reports',
            'No matching linked report returned by the connected searches.' if complete_search else
            'Report verification incomplete: a search failed, is not connected, or has no verified search status. This is not evidence that no report exists.', now, kind='note')
    for name in unavailable:
        add('C', name, 'Source unavailable or not connected; this check cannot confirm or rule out a fire.', now, kind='note')
    if news_failed:
        add('C', 'News search', 'News search unavailable; no negative conclusion can be drawn.', now, kind='note')

    categories = {NEWS_CATEGORY[m['incident_type']] for m in reports if m.get('incident_type') in NEWS_CATEGORY}
    decided = len(categories) == 1
    category = next(iter(categories)) if decided else 'unknown'
    kind_label = f'Official report: {CATEGORY_LABEL[category]}' if decided else 'Unknown (not verified)'
    kind_note = ('Type comes from a linked matching official report, not land use or missing detections.' if decided else
                 'No single fire type is established by linked official reports. Land cover and missing detections do not identify a fire type.')
    reality = 'Official report matched' if reports else 'No external confirmation yet'
    reality_basis = (f'{len(reports)} linked official report(s) matched this location and time; inspect sources to verify event association.' if reports else
                     'Satellite heat detections are recorded. Available connected sources have not established independent fire confirmation; unavailable sources remain unchecked.')
    since = max(0, (now - last).total_seconds() / 3600)
    now_basis = f'Last recorded heat detection: {_iso(last)} ({since:.1f} h before this check). Current burning or extinction is not established by the available observations.'
    pending = sorted(set(orbits['witnesses']) - {p['witness'] for p in observed if p['time'] > first})
    return {
        'data_policy': 'source-backed-v2', 'checked_at': _iso(now),
        'case_id': subject.get('event_id') or f'HS-{lat:.3f}-{lon:.3f}-{first:%Y%m%d%H%M}',
        'opened_at': _iso(first), 'closes_at': _iso(closes), 'status': 'closed' if now >= closes else 'open',
        'provisional': True, 'pending_witnesses': [WITNESS_LABEL[w] for w in pending],
        'answer': {'is_real': {'label': reality, 'basis': reality_basis},
                   'kind': {'category': category, 'label': kind_label, 'decided': decided, 'basis': kind_note},
                   'now': {'label': 'Unknown', 'basis': now_basis}},
        'category_scores': [],
        'decision_rules': dict(min_top_score=0, min_lead=0, top=category, top_score=0, lead=0, passed=decided),
        'satellite_fire_probability': dict(probability=None, prior=None, passes_used=len(observed),
            method='Withheld: no validated event-specific fire probability is available.'),
        'passes': [{**p, 'time': _iso(p['time'])} for p in passes],
        'next_passes': [dict(label=p['label'], time=_iso(p['time']), swath_position=p['swath_position']) for p in future[:4]],
        'overpass_method': orbits['method'], 'overpass_errors': orbits['errors'], 'geostationary': geo,
        'burning_season': dict(status='not_used', note='Historical recurrence does not establish event type or current state.'),
        'evidence_block': sorted(items, key=lambda i: i['time'] or ''),
        'explanation': f'{reality_basis} {kind_note} {now_basis}',
        'marker': dict(kind=category, reality=reality, state='Unknown', provisional=True),
        'situations': dict(coverage='Missing FIRMS hotspots do not establish a clear view or extinction.',
            predictions='Orbit predictions are estimates, not observations. Nominal fallback schedules are withheld.',
            merged_alerts=f'{len(dets)} detection record(s) linked by the event matcher.'),
        'streams': {'pending': pending_streams,
            'A': dict(status='done', passes_observed=len(observed), passes_expected=len(future)),
            'B': dict(status=geo['status']), 'C': dict(status=report_status, reports=len(reports) + len(articles))},
        'score_note': 'Unvalidated category weights and detection probabilities are withheld. Linked official reports supply reported fire types.',
    }
