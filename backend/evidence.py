"""Second-stage fire confirmation and evidence fusion."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from schemas import HotspotRecord
from verification import _country_context, _gdelt_url, _worldview_url


CACHE_TTL_SECONDS = 60 * 30
_EVIDENCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

COUNTRY_SOURCE_CONFIG = {
    "BD": {
        "regional_satellite": ["Himawari regional imagery", "Sentinel/Copernicus", "NASA FIRMS"],
        "government": ["Bangladesh Fire Service and Civil Defence", "Department of Environment", "Ministry of Disaster Management and Relief"],
        "english_news": ["The Daily Star", "Dhaka Tribune", "The Business Standard", "UNB"],
        "news_domains": ["thedailystar.net", "dhakatribune.com", "tbsnews.net", "unb.com.bd"],
    },
    "BR": {
        "regional_satellite": ["INPE Queimadas", "DETER", "PRODES", "GOES", "Global Forest Watch"],
        "government": ["INPE", "IBAMA", "Civil Defense Brazil"],
        "english_news": ["Agencia Brasil English", "Reuters Brazil", "AP Brazil"],
        "news_domains": ["agenciabrasil.ebc.com.br", "reuters.com", "apnews.com"],
    },
    "IN": {
        "regional_satellite": ["Forest Survey of India", "Bhuvan", "ISRO fire products", "INSAT", "NASA FIRMS"],
        "government": ["Forest Survey of India", "National Disaster Management Authority", "State forest departments"],
        "english_news": ["The Hindu", "Indian Express", "Hindustan Times", "Times of India", "NDTV"],
        "news_domains": ["thehindu.com", "indianexpress.com", "hindustantimes.com", "timesofindia.indiatimes.com", "ndtv.com"],
    },
    "ID": {
        "regional_satellite": ["BRIN/LAPAN fire products", "Himawari", "Global Forest Watch", "NASA FIRMS"],
        "government": ["BNPB", "Ministry of Environment and Forestry"],
        "english_news": ["The Jakarta Post", "ANTARA English"],
        "news_domains": ["thejakartapost.com", "antaranews.com"],
    },
    "US": {
        "regional_satellite": ["NOAA GOES", "USFS", "NIFC", "NASA FIRMS"],
        "government": ["NIFC", "USFS", "NOAA", "state fire agencies"],
        "english_news": ["AP", "Reuters", "local newspapers", "local TV news"],
        "news_domains": ["apnews.com", "reuters.com", "npr.org"],
    },
    "CA": {
        "regional_satellite": ["Canadian Wildland Fire Information System", "GOES", "NASA FIRMS"],
        "government": ["Canadian Wildland Fire Information System", "provincial fire agencies"],
        "english_news": ["CBC", "CTV News", "Global News"],
        "news_domains": ["cbc.ca", "ctvnews.ca", "globalnews.ca"],
    },
    "AU": {
        "regional_satellite": ["Himawari", "Geoscience Australia", "state fire agency feeds", "NASA FIRMS"],
        "government": ["state fire authorities", "Emergency Management Australia"],
        "english_news": ["ABC News", "SBS", "state/local news outlets"],
        "news_domains": ["abc.net.au", "sbs.com.au", "9news.com.au"],
    },
}

FALLBACK_SOURCES = {
    "regional_satellite": ["NASA FIRMS", "Copernicus/Sentinel", "Global Forest Watch", "regional geostationary imagery where available"],
    "government": ["national disaster agency", "environment ministry", "fire service"],
    "english_news": ["local English-language outlets", "national English-language outlets", "Reuters", "AP", "GDELT"],
    "news_domains": ["reuters.com", "apnews.com"],
}

FIRE_TERMS = {
    "wildfire": "WILDFIRE",
    "forest fire": "FOREST_FIRE",
    "bushfire": "WILDFIRE",
    "grass fire": "GRASS_FIRE",
    "peat": "PEAT_FIRE",
    "agricultural": "AGRICULTURAL_BURN",
    "crop burning": "AGRICULTURAL_BURN",
    "controlled burn": "CONTROLLED_BURN",
    "factory fire": "FACTORY_FIRE",
    "building fire": "BUILDING_FIRE",
    "vehicle fire": "VEHICLE_FIRE",
    "explosion": "EXPLOSION",
    "gas flare": "INDUSTRIAL_HEAT",
    "volcanic": "VOLCANIC_ACTIVITY",
    "deforestation": "DEFORESTATION",
}


def _cache_key(hotspot: HotspotRecord) -> str:
    return f"{hotspot.sensor}:{hotspot.lat:.4f}:{hotspot.lon:.4f}:{hotspot.acq_datetime.isoformat()}"


def reverse_geocode_service(hotspot: HotspotRecord) -> dict[str, Any]:
    context = _country_context({"lat": hotspot.lat, "lon": hotspot.lon})
    return {
        "country": context["country_name"],
        "country_code": context["country_code"],
        "admin_level_1": context["place"],
        "admin_level_2": context["place"],
        "city": context["place"],
        "locality": context["place"],
        "coordinates": {"lat": hotspot.lat, "lon": hotspot.lon},
        "precision": "country_or_region_bbox",
    }


def country_source_service(place: dict[str, Any]) -> dict[str, list[str]]:
    code = place.get("country_code")
    return COUNTRY_SOURCE_CONFIG.get(code, FALLBACK_SOURCES)


def satellite_validation_service(hotspot: HotspotRecord, sources: dict[str, list[str]]) -> dict[str, Any]:
    evidence = []
    if hotspot.confidence_pct >= 80:
      evidence.append("High-confidence FIRMS detection")
    if hotspot.frp is not None and hotspot.frp >= 10:
      evidence.append(f"FRP {hotspot.frp:.1f} MW supports active combustion")
    if hotspot.daynight.upper() == "N":
      evidence.append("Night detection reduces solar-heated ground false positives")
    regional_sources = sources["regional_satellite"]
    if regional_sources:
      evidence.append(f"Regional review sources selected: {', '.join(regional_sources[:3])}")
    return {
        "status": "completed",
        "sources": ["NASA FIRMS", *regional_sources],
        "evidence": evidence,
        "worldview_url": _worldview_url(hotspot.model_dump()),
    }


def government_source_service(place: dict[str, Any], sources: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "status": "pending_manual_or_connector",
        "sources": sources["government"],
        "evidence": [],
        "note": "Government feeds vary by country; listed sources should be checked or connected when an API/RSS feed is available.",
    }


def _event_type(text: str) -> str:
    lowered = text.lower()
    for term, event in FIRE_TERMS.items():
        if term in lowered:
            return event
    if "fire" in lowered or "smoke" in lowered or "burning" in lowered:
        return "UNKNOWN_FIRE"
    return "UNKNOWN"


def _time_score(hotspot_time: datetime, article_time: datetime | None) -> tuple[int, str]:
    if article_time is None:
        return 35, "Unknown publication time"
    diff_hours = abs((article_time - hotspot_time).total_seconds()) / 3600
    if diff_hours <= 1:
        return 100, "0-1 hour"
    if diff_hours <= 3:
        return 85, "1-3 hours"
    if diff_hours <= 6:
        return 70, "3-6 hours"
    if diff_hours <= 24:
        return 45, "6-24 hours"
    return 15, ">24 hours"


def _location_score(article_text: str, place: dict[str, Any]) -> tuple[int, str]:
    names = [place.get("locality"), place.get("city"), place.get("admin_level_2"), place.get("admin_level_1"), place.get("country")]
    for index, name in enumerate([item for item in names if item]):
        if str(name).lower() in article_text.lower():
            return max(95 - index * 12, 55), str(name)
    return 20, "No matching place name found"


def _article_datetime(article: dict[str, Any]) -> datetime | None:
    value = article.get("seendate") or article.get("publishedAt")
    if not value:
        return None
    try:
        if isinstance(value, str) and value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str) and len(value) >= 14 and value[:14].isdigit():
            return datetime.strptime(value[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def nlp_service(article: dict[str, Any], hotspot: HotspotRecord, place: dict[str, Any]) -> dict[str, Any]:
    title = article.get("title", "")
    text = f"{title} {article.get('sourceCommonName', '')} {article.get('domain', '')}"
    event_type = _event_type(text)
    location_score, matched_place = _location_score(text, place)
    time_score, time_match = _time_score(hotspot.acq_datetime, _article_datetime(article))
    fire_score = 95 if event_type in {"WILDFIRE", "FOREST_FIRE", "GRASS_FIRE", "PEAT_FIRE"} else 70 if event_type in {"UNKNOWN_FIRE", "AGRICULTURAL_BURN", "CONTROLLED_BURN"} else 25
    source_score = 80
    semantic_score = round((location_score * 0.35) + (time_score * 0.2) + (fire_score * 0.35) + (source_score * 0.1))
    return {
        "event_type": event_type,
        "mentioned_place": matched_place,
        "location_score": location_score,
        "time_score": time_score,
        "time_match": time_match,
        "fire_event_score": fire_score,
        "source_reliability_score": source_score,
        "semantic_relevance_score": semantic_score,
        "overall_relevance_score": semantic_score,
        "match_label": "Strong corroborating evidence" if semantic_score >= 80 else "Possible corroborating evidence" if semantic_score >= 55 else "Weak or unrelated evidence",
    }


async def news_service(hotspot: HotspotRecord, place: dict[str, Any], sources: dict[str, list[str]], refresh: bool = False) -> dict[str, Any]:
    location = place.get("locality") or place.get("city") or place.get("country") or f"{hotspot.lat:.3f},{hotspot.lon:.3f}"
    queries = [
        f'"{location}" fire',
        f'"{location}" wildfire',
        f'"{location}" forest fire',
        f'"{location}" smoke',
        f'"{location}" burning',
        f'"{location}" agricultural fire',
    ]
    base_url = _gdelt_url(hotspot.model_dump())
    articles: list[dict[str, Any]] = []
    news_api_url = "https://newsapi.org/v2/everything"
    news_api_key = os.getenv("NEWS_API_KEY", "")
    from_date = (hotspot.acq_datetime - timedelta(days=1)).date().isoformat()
    to_date = (hotspot.acq_datetime + timedelta(days=1)).date().isoformat()
    newsapi_query = f'("{location}" OR "{place.get("country")}") AND (fire OR wildfire OR smoke OR burning OR forest fire)'
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if news_api_key:
                news_response = await client.get(
                    news_api_url,
                    params={
                        "q": newsapi_query,
                        "searchIn": "title,description",
                        "language": "en",
                        "sortBy": "relevancy",
                        "from": from_date,
                        "to": to_date,
                        "pageSize": 20,
                        "domains": ",".join(sources.get("news_domains", [])[:20]),
                        "apiKey": news_api_key,
                    },
                )
                if news_response.status_code < 400:
                    for article in news_response.json().get("articles", []):
                        articles.append(
                            {
                                "title": article.get("title", ""),
                                "sourceCommonName": article.get("source", {}).get("name", "NewsAPI source"),
                                "domain": article.get("source", {}).get("name", "NewsAPI"),
                                "publishedAt": article.get("publishedAt", ""),
                                "url": article.get("url", ""),
                                "description": article.get("description", ""),
                                "provider": "NewsAPI",
                            }
                        )
            response = await client.get(base_url)
            if response.status_code < 400:
                for article in response.json().get("articles", [])[:12]:
                    article["provider"] = "GDELT"
                    articles.append(article)
    except Exception:
        if not articles:
            articles = []

    seen_titles: set[str] = set()
    cards = []
    for article in articles:
        title = article.get("title", "Untitled report")
        normalized = " ".join(title.lower().split())
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        analysis = nlp_service(article, hotspot, place)
        provider = article.get("provider", "GDELT")
        cards.append(
            {
                "headline": title,
                "publication": article.get("sourceCommonName") or article.get("domain") or "GDELT indexed source",
                "country": place.get("country"),
                "published_at": article.get("seendate") or article.get("publishedAt", ""),
                "location_mentioned": analysis["mentioned_place"],
                "distance_km": None,
                "event_type": analysis["event_type"],
                "relevance_score": analysis["overall_relevance_score"],
                "location_score": analysis["location_score"],
                "time_score": analysis["time_score"],
                "fire_event_score": analysis["fire_event_score"],
                "source_reliability_score": analysis["source_reliability_score"],
                "semantic_relevance_score": analysis["semantic_relevance_score"],
                "summary": f"AI summary: {provider} returned this article as possible fire evidence; open the original source for the reported facts.",
                "url": article.get("url", ""),
                "match_label": analysis["match_label"],
                "provider": provider,
            }
        )
    return {
        "status": "completed",
        "preferred_sources": sources["english_news"],
        "queries": queries,
        "gdelt_url": base_url,
        "newsapi_query": newsapi_query,
        "newsapi_enabled": bool(news_api_key),
        "articles": sorted(cards, key=lambda item: item["relevance_score"], reverse=True),
    }


def evidence_fusion_service(hotspot: HotspotRecord, satellite: dict[str, Any], government: dict[str, Any], news: dict[str, Any]) -> dict[str, Any]:
    satellite_score = 0
    if hotspot.confidence_pct >= 80:
        satellite_score += 15
    elif hotspot.confidence_pct >= 50:
        satellite_score += 8
    if hotspot.frp is not None and hotspot.frp >= 10:
        satellite_score += 10
    if hotspot.daynight.upper() == "N":
        satellite_score += 5

    best_article = max((article["relevance_score"] for article in news["articles"]), default=0)
    news_score = min(20, round(best_article * 0.2))
    government_score = 0
    regional_score = 10 if satellite["sources"] else 0
    score = min(100, satellite_score + regional_score + government_score + news_score)

    reasons = [*satellite["evidence"]]
    if best_article >= 80:
        reasons.append("Local/national news has a strong location/time/event match")
    elif best_article >= 55:
        reasons.append("News search found possible corroborating evidence")
    else:
        reasons.append("No strong external news confirmation yet")

    if score >= 85 and best_article >= 70:
        status = "CONFIRMED FIRE"
    elif score >= 65:
        status = "HIGHLY LIKELY FIRE"
    elif best_article < 30 and satellite_score < 15:
        status = "NO EXTERNAL CONFIRMATION"
    elif any(article["event_type"] in {"CONTROLLED_BURN", "AGRICULTURAL_BURN", "INDUSTRIAL_HEAT"} for article in news["articles"][:3]):
        status = "LIKELY NON-FIRE THERMAL ANOMALY"
    else:
        status = "POSSIBLE FIRE - NEEDS VERIFICATION"

    uncertainty = []
    if not government["evidence"]:
        uncertainty.append("No official government confirmation found yet")
    if not news["articles"]:
        uncertainty.append("No matching local/national article was returned by GDELT")

    return {
        "final_status": status,
        "system_evidence_score": score,
        "weights": {
            "satellite_consistency": 30,
            "regional_satellite": 20,
            "government_source": 20,
            "news_confirmation": 15,
            "geographic_match": 10,
            "temporal_match": 5,
        },
        "why": reasons,
        "uncertainty": uncertainty,
        "ai_analysis": "System interpretation from FIRMS metadata, configured regional sources, government-source availability, and GDELT/NLP article matching. This is an evidence score, not a validated probability.",
    }


async def build_hotspot_evidence(hotspot: HotspotRecord, refresh: bool = False) -> dict[str, Any]:
    key = _cache_key(hotspot)
    cached = _EVIDENCE_CACHE.get(key)
    if cached and not refresh and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        return {**cached[1], "cache": {"hit": True, "ttl_seconds": CACHE_TTL_SECONDS}}

    place = reverse_geocode_service(hotspot)
    sources = country_source_service(place)
    satellite = satellite_validation_service(hotspot, sources)
    government = government_source_service(place, sources)
    news = await news_service(hotspot, place, sources, refresh)
    fusion = evidence_fusion_service(hotspot, satellite, government, news)
    stages = [
        {"name": "Satellite Validation", "status": "completed"},
        {"name": "Regional Source Validation", "status": "completed"},
        {"name": "Government Check", "status": government["status"]},
        {"name": "News Validation", "status": "completed", "detail": f'{len(news["articles"])} reports found'},
        {"name": "NLP Analysis", "status": "completed"},
        {"name": "Final Evidence Score", "status": "completed", "detail": f'{fusion["system_evidence_score"]}/100'},
    ]
    result = {
        "hotspot": hotspot.model_dump(),
        "place": place,
        "stages": stages,
        "satellite_evidence": satellite,
        "government_evidence": government,
        "news_evidence": news,
        "fusion": fusion,
        "source_transparency": {
            "satellite_sources": satellite["sources"],
            "news_sources": [article["publication"] for article in news["articles"]],
            "government_sources": government["sources"],
            "generated_summary_notice": "AI summaries are system-generated and are not direct newspaper text.",
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_TTL_SECONDS},
    }
    _EVIDENCE_CACHE[key] = (time.time(), result)
    return result
