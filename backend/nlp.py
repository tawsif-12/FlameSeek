"""Rule-based NLP for news articles and official reports.

Extracts location mentions, dates/times, event type, cause, impact, affected
area and infrastructure from headline + description text, so an article is only
counted as fire evidence when it actually describes a matching fire event.
This is transparent pattern matching, not a trained language model.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any


# Ordered: the first matching category wins, most specific first.
EVENT_PATTERNS: list[tuple[str, str]] = [
    ("VOLCANIC_ACTIVITY", r"\b(volcan\w*|eruption|lava)\b"),
    ("GAS_FLARE", r"\b(gas flar\w*|flaring|flare stack)\b"),
    ("INDUSTRIAL_HEAT_SOURCE", r"\b(refinery|steel ?(plant|mill)|smelter|blast furnace|industrial (fire|blaze|heat)|power plant fire)\b"),
    ("FACTORY_FIRE", r"\b(factory|warehouse|mill|plant) (fire|blaze|caught fire)|fire (at|in) (a |the )?(factory|warehouse|garment|chemical)"),
    ("BUILDING_FIRE", r"\b(house|home|building|apartment|market|shop|hospital|slum|tower) (fire|blaze)|fire (broke out )?(at|in) (a |the )?(house|building|apartment|market|slum)"),
    ("CONTROLLED_BURN", r"\b(controlled|prescribed|planned|hazard[- ]reduction|pile) (burn\w*|fire)|\bback-?burn\w*"),
    ("AGRICULTURAL_BURN", r"\b(stubble|crop|paddy|straw|residue|sugarcane|field|farm|agricultural) (burn\w*|fire\w*)|\bburning (of )?(stubble|crop|paddy|straw|residue)"),
    ("DEFORESTATION_RELATED_BURNING", r"\b(deforestation|illegal (clearing|logging)).{0,40}\b(fire|burn\w*)|\b(fire|burn\w*).{0,40}\bdeforestation"),
    ("LAND_CLEARING", r"\b(land[- ]clearing|slash[- ]and[- ]burn|clearing (land|forest) by fire|swidden)"),
    ("FOREST_FIRE", r"\b(forest|jungle|woodland|peat(land)?) (fire|blaze)s?\b|\bfire\w* in (the )?(forest|jungle|peat)"),
    ("WILDFIRE", r"\b(wildfire|bushfire|bush fire|brush ?fire|grass ?fire|veld ?fire|wildland fire|scrub fire|hill fire)s?\b"),
]
GENERIC_FIRE = r"\b(fire|fires|blaze|blazes|burning|smoke|flames|inferno|hotspot)\b"
# Uses of "fire" that do not describe combustion.
NEGATIVE_PATTERNS = r"\b(cease-?fire|gun ?fire|opened fire|open fire on|fired (from|by|at|as|over)|was fired|under fire|fire sale|firearm|firework|fire(d)? (a )?(missile|rocket|shot)|crossfire|firefight|hire and fire|fire(d)? (an? )?(employee|coach|ceo|manager)|set the (stage|internet) on fire|on fire (form|streak))\b"

CAUSE_PATTERNS = {
    "lightning": r"\blightning\b",
    "arson": r"\b(arson|arsonist|deliberately (lit|set)|set on fire intentionally)\b",
    "agricultural burning": r"\b(stubble|crop residue|farm(ers)? burn\w*|slash[- ]and[- ]burn)\b",
    "prescribed / controlled burn": r"\b(prescribed|controlled|hazard[- ]reduction) burn\w*",
    "land clearing": r"\b(land[- ]clearing|clearing land)\b",
    "electrical fault": r"\b(short[- ]circuit|electrical fault|power ?line)\b",
    "gas leak / explosion": r"\b(gas (leak|cylinder)|explosion|exploded|boiler)\b",
    "discarded cigarette / campfire": r"\b(cigarette|campfire|bonfire|barbecue)\b",
    "heatwave / drought": r"\b(heat ?wave|drought|dry (conditions|spell))\b",
    "human activity (unspecified)": r"\b(human activity|man-made|human-caused|accidental(ly)?)\b",
}
INFRASTRUCTURE_PATTERNS = {
    "road / highway": r"\b(road|highway|motorway|freeway|route \d+)\b",
    "railway": r"\b(rail(way)?|train line)\b",
    "power line / grid": r"\b(power ?line|transmission line|substation|power grid|electricity)\b",
    "homes / settlements": r"\b(homes?|houses?|villages?|residential|settlements?|properties)\b",
    "school": r"\bschools?\b",
    "hospital / clinic": r"\b(hospitals?|clinics?|health cent(er|re))\b",
    "factory / industrial site": r"\b(factory|factories|plant|refinery|warehouse|industrial)\b",
    "pipeline": r"\bpipeline\b",
    "airport": r"\bairport\b",
    "farmland": r"\b(farmland|crops?|plantation|orchard|pasture)\b",
    "protected area / park": r"\b(national park|reserve|sanctuary|protected area)\b",
}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], start=1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

LOCATION_CUE = re.compile(r"\b(?:in|near|at|outside|around|across|from|of)\s+((?:[A-Z][a-zA-Z'\-]+)(?:\s+(?:[A-Z][a-zA-Z'\-]+|de|do|da|del|of)){0,3})")
STOP_LOCATIONS = {"The", "A", "An", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "Fire", "Police", "Officials"}


def classify_event(text: str) -> dict[str, Any]:
    lowered = text.lower()
    negatives = re.findall(NEGATIVE_PATTERNS, lowered)
    for label, pattern in EVENT_PATTERNS:
        m = re.search(pattern, lowered)
        if m:
            return {"event_type": label, "matched_phrase": m.group(0), "is_fire_related": True}
    generic = re.search(GENERIC_FIRE, lowered)
    if generic and not negatives:
        return {"event_type": "UNKNOWN_THERMAL_EVENT", "matched_phrase": generic.group(0), "is_fire_related": True}
    if generic and negatives:
        # Every "fire" mention is explained by a non-combustion idiom.
        return {"event_type": "NOT_A_FIRE_EVENT", "matched_phrase": negatives[0] if isinstance(negatives[0], str) else negatives[0][0], "is_fire_related": False}
    return {"event_type": "NOT_A_FIRE_EVENT", "matched_phrase": None, "is_fire_related": False}


def _dates_in_text(text: str, reference: date) -> list[date]:
    found: list[date] = []
    lowered = text.lower()
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\.?\b(?:,?\s+(\d{{4}}))?", lowered):
        found += _mk_date(int(m.group(1)), MONTHS[m.group(2)], m.group(3), reference)
    for m in re.finditer(rf"\b({month_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", lowered):
        found += _mk_date(int(m.group(2)), MONTHS[m.group(1)], m.group(3), reference)
    if re.search(r"\byesterday\b", lowered):
        found.append(reference - timedelta(days=1))
    if re.search(r"\b(today|tonight|this morning|this afternoon)\b", lowered):
        found.append(reference)
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b(on )?{name}\b", lowered):
            delta = (reference.weekday() - i) % 7
            found.append(reference - timedelta(days=delta))
    return sorted(set(found))


def _mk_date(day: int, month: int, year: str | None, reference: date) -> list[date]:
    try:
        d = date(int(year) if year else reference.year, month, day)
    except ValueError:
        return []
    if not year and d > reference + timedelta(days=2):
        d = d.replace(year=d.year - 1)
    return [d]


def extract(text: str, published: datetime | None, place_names: list[str]) -> dict[str, Any]:
    """Structured facts from article text. place_names: gazetteer from reverse geocoding."""
    lowered = text.lower()
    classification = classify_event(text)
    gazetteer_hits = [name for name in place_names if name and len(name) > 2 and re.search(rf"\b{re.escape(name.lower())}\b", lowered)]
    cue_hits = []
    for m in LOCATION_CUE.finditer(text):
        candidate = m.group(1).strip()
        if candidate.split()[0] not in STOP_LOCATIONS and candidate not in cue_hits:
            cue_hits.append(candidate)
    reference = (published or datetime.now(timezone.utc)).date()
    event_dates = _dates_in_text(text, reference)
    times = re.findall(r"\b(\d{1,2}(?::\d{2})?\s?(?:a\.?m\.?|p\.?m\.?)|\d{1,2}:\d{2}(?:\s?(?:gmt|utc|local time))?)\b", lowered)
    area = re.findall(r"(\d[\d,\.]*)\s*(hectares|hectare|ha|acres|acre|square kilomet(?:er|re)s|sq km|km2)\b", lowered)
    deaths = re.findall(r"(\d+)\s+(?:people\s+|persons\s+)?(?:were\s+)?(?:killed|dead|died|deaths)", lowered)
    injured = re.findall(r"(\d+)\s+(?:people\s+|persons\s+)?(?:were\s+)?(?:injured|hurt|hospitali[sz]ed)", lowered)
    evac = re.findall(r"(\d[\d,]*)\s+(?:people|residents|families|households)?\s*(?:were\s+)?evacuat\w+", lowered)
    homes = re.findall(r"(\d+)\s+(?:homes|houses|buildings|structures)\s+(?:were\s+)?(?:destroyed|damaged|burn\w*|gutted)", lowered)
    impact = {
        "deaths": sum(int(x) for x in deaths) or None,
        "injured": sum(int(x) for x in injured) or None,
        "evacuated": sum(int(x.replace(",", "")) for x in evac) or (True if "evacuat" in lowered else None),
        "structures_damaged": sum(int(x) for x in homes) or None,
    }
    return {
        **classification,
        "locations": {"gazetteer_matches": gazetteer_hits, "other_place_mentions": cue_hits[:5]},
        "dates_mentioned": [d.isoformat() for d in event_dates],
        "times_mentioned": times[:3],
        "causes": [c for c, p in CAUSE_PATTERNS.items() if re.search(p, lowered)],
        "impact": {k: v for k, v in impact.items() if v},
        "affected_area": [f"{a} {u}" for a, u in area][:3],
        "infrastructure_mentioned": [k for k, p in INFRASTRUCTURE_PATTERNS.items() if re.search(p, lowered)],
    }


def system_summary(facts: dict[str, Any], match: dict[str, Any]) -> str:
    """Short rule-based summary built only from extracted facts (never article text)."""
    kind = facts["event_type"].replace("_", " ").lower()
    where = (facts["locations"]["gazetteer_matches"] or facts["locations"]["other_place_mentions"] or ["an unspecified location"])[0]
    parts = [f"Describes a {kind} at/near {where}"]
    if match.get("distance_km") is not None:
        parts.append(f"about {match['distance_km']:.0f} km from the satellite event")
    if match.get("hours_after_detection") is not None:
        h = match["hours_after_detection"]
        parts.append(f"published {abs(h):.1f} h {'after' if h >= 0 else 'before'} the detection")
    s = ", ".join(parts) + "."
    if facts["causes"]:
        s += f" Cause mentioned: {', '.join(facts['causes'][:2])}."
    if facts["affected_area"]:
        s += f" Area mentioned: {facts['affected_area'][0]}."
    impact = facts.get("impact") or {}
    if impact:
        s += " Impact: " + ", ".join(f"{k.replace('_', ' ')} {v if v is not True else 'reported'}" for k, v in impact.items()) + "."
    return s
