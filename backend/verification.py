"""Rule-based active-fire verification helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus


COUNTRY_AREAS = [
    {"code": "BD", "fips": "BG", "name": "Bangladesh", "place": "Bangladesh", "bbox": (88.0, 20.5, 92.8, 26.7)},
    {"code": "BR", "fips": "BR", "name": "Brazil", "place": "Brazil", "bbox": (-74.0, -34.0, -34.0, 5.5)},
    {"code": "ID", "fips": "ID", "name": "Indonesia", "place": "Indonesia", "bbox": (95.0, -11.5, 141.5, 6.5)},
    {"code": "IN", "fips": "IN", "name": "India", "place": "India", "bbox": (68.0, 6.0, 97.5, 37.5)},
    {"code": "US", "fips": "US", "name": "United States", "place": "United States", "bbox": (-125.0, 24.0, -66.0, 49.5)},
    {"code": "CA", "fips": "CA", "name": "Canada", "place": "Canada", "bbox": (-141.0, 41.5, -52.0, 83.0)},
    {"code": "AU", "fips": "AS", "name": "Australia", "place": "Australia", "bbox": (112.0, -44.0, 154.0, -10.0)},
    {"code": "RU", "fips": "RS", "name": "Russia", "place": "Russia", "bbox": (19.0, 41.0, 180.0, 82.0)},
    {"code": "CN", "fips": "CH", "name": "China", "place": "China", "bbox": (73.0, 18.0, 135.5, 54.0)},
    {"code": "GR", "fips": "GR", "name": "Greece", "place": "Greece", "bbox": (19.0, 34.0, 29.8, 42.2)},
    {"code": "TR", "fips": "TU", "name": "Turkey", "place": "Turkey", "bbox": (25.5, 35.5, 45.0, 42.5)},
    {"code": "MX", "fips": "MX", "name": "Mexico", "place": "Mexico", "bbox": (-118.5, 14.0, -86.5, 33.5)},
    {"code": "AR", "fips": "AR", "name": "Argentina", "place": "Argentina", "bbox": (-73.6, -55.2, -53.6, -21.7)},
    {"code": "CL", "fips": "CI", "name": "Chile", "place": "Chile", "bbox": (-76.0, -56.0, -66.0, -17.5)},
    {"code": "BO", "fips": "BL", "name": "Bolivia", "place": "Bolivia", "bbox": (-70.0, -23.0, -57.0, -9.5)},
    {"code": "PE", "fips": "PE", "name": "Peru", "place": "Peru", "bbox": (-82.0, -18.5, -68.5, 0.0)},
    {"code": "CO", "fips": "CO", "name": "Colombia", "place": "Colombia", "bbox": (-79.5, -4.5, -66.5, 13.5)},
    {"code": "VE", "fips": "VE", "name": "Venezuela", "place": "Venezuela", "bbox": (-73.5, 0.5, -59.5, 12.5)},
    {"code": "CD", "fips": "CG", "name": "Democratic Republic of the Congo", "place": "DR Congo", "bbox": (12.0, -13.5, 31.5, 5.5)},
    {"code": "ZA", "fips": "SF", "name": "South Africa", "place": "South Africa", "bbox": (16.0, -35.0, 33.0, -22.0)},
]


def _sensor_label(sensor: str) -> str:
    if sensor == "modis":
        return "MODIS"
    return "VIIRS"


def _worldview_url(row: dict[str, Any]) -> str:
    lat = float(row["lat"])
    lon = float(row["lon"])
    when: datetime = row["acq_datetime"]
    west = lon - 0.35
    south = lat - 0.35
    east = lon + 0.35
    north = lat + 0.35
    layer = "MODIS_Terra_CorrectedReflectance_TrueColor" if row["sensor"] == "modis" else "VIIRS_SNPP_CorrectedReflectance_TrueColor"
    return (
        "https://worldview.earthdata.nasa.gov/"
        f"?v={west:.4f},{south:.4f},{east:.4f},{north:.4f}"
        f"&l={layer},Reference_Labels_15m,Reference_Features_15m"
        f"&t={when.date().isoformat()}"
    )


def _gdelt_url(row: dict[str, Any]) -> str:
    geo = _country_context(row)
    lat = float(row["lat"])
    lon = float(row["lon"])
    when: datetime = row["acq_datetime"]
    start = (when - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    end = (when + timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    location_terms = f'"{geo["place"]}" OR "{geo["country_name"]}"' if geo["country_code"] else f"near:{lat:.3f},{lon:.3f},50km"
    source_country = f' sourcecountry:{geo["fips_code"]}' if geo["fips_code"] else ""
    query = quote_plus(f'(fire OR wildfire OR burning OR smoke) ({location_terms}){source_country}')
    return f"https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=artlist&format=json&startdatetime={start}&enddatetime={end}"


def _country_context(row: dict[str, Any]) -> dict[str, str | None]:
    lat = float(row["lat"])
    lon = float(row["lon"])
    for country in COUNTRY_AREAS:
        west, south, east, north = country["bbox"]
        if west <= lon <= east and south <= lat <= north:
            return {
                "country_code": country["code"],
                "country_name": country["name"],
                "fips_code": country["fips"],
                "place": country["place"],
            }
    return {"country_code": None, "country_name": "Unknown", "fips_code": None, "place": f"{lat:.3f}, {lon:.3f}"}


def verify_hotspot(row: dict[str, Any]) -> dict[str, Any]:
    """Score a FIRMS row with fast metadata checks and verification links."""

    score = 0
    evidence: list[dict[str, str | int | float]] = []
    warnings: list[str] = []
    confidence = float(row.get("confidence_pct") or 0)
    frp = row.get("frp")
    daynight = str(row.get("daynight") or "").upper()
    country_context = _country_context(row)

    if confidence >= 80:
        score += 2
        evidence.append({"source": "FIRMS confidence", "signal": "High sensor confidence", "weight": 2})
    elif confidence >= 50:
        score += 1
        evidence.append({"source": "FIRMS confidence", "signal": "Nominal sensor confidence", "weight": 1})
    else:
        warnings.append("Low confidence detection; prioritize imagery review.")

    if frp is not None and float(frp) >= 10:
        score += 2
        evidence.append({"source": "FIRMS FRP", "signal": f"FRP {float(frp):.1f} MW is consistent with active combustion", "weight": 2})
    elif frp is not None and float(frp) >= 5:
        score += 1
        evidence.append({"source": "FIRMS FRP", "signal": f"FRP {float(frp):.1f} MW is moderate", "weight": 1})
    else:
        warnings.append("Low or missing FRP can indicate weak fire, obscuration, or a false positive.")

    if daynight == "N":
        score += 2
        evidence.append({"source": "Day/night flag", "signal": "Night detection reduces solar-heated bare-ground false positives", "weight": 2})
    elif daynight == "D":
        warnings.append("Daytime-only detections need smoke, persistence, or local corroboration.")

    if str(row.get("sensor", "")).startswith("viirs"):
        score += 1
        evidence.append({"source": "Sensor resolution", "signal": "VIIRS 375 m detection is finer than MODIS 1 km", "weight": 1})

    if score >= 6:
        verdict = "confirmed_fire"
    elif score <= 2:
        verdict = "likely_false_positive"
    else:
        verdict = "needs_review"

    return {
        **row,
        "verification": {
            "score": score,
            "verdict": verdict,
            "evidence": evidence,
            "warnings": warnings,
            "imagery_url": _worldview_url(row),
            "news_url": _gdelt_url(row),
            "national_news_url": _gdelt_url(row),
            "country_code": country_context["country_code"],
            "country_name": country_context["country_name"],
            "place_name": country_context["place"],
            "next_step": "Open imagery/news links for smoke, burn scar, or local report confirmation." if verdict == "needs_review" else "Use imagery/news links as audit trail.",
            "sensor_family": _sensor_label(str(row.get("sensor", ""))),
        },
    }
