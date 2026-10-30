"""Country-specific evidence sources: regional satellites, official agencies, English news.

"automated" sources are queried by the backend. Everything else is listed with a
link so an analyst can check it; the app never claims to have checked a source
it only links to.
"""

from __future__ import annotations

from typing import Any


COUNTRY_SOURCES: dict[str, dict[str, Any]] = {
    "BD": {
        "government": [
            {"name": "Bangladesh Fire Service and Civil Defence", "url": "https://fireservice.gov.bd/"},
            {"name": "Department of Environment", "url": "https://doe.gov.bd/"},
            {"name": "Ministry of Disaster Management and Relief", "url": "https://modmr.gov.bd/"},
        ],
        "national_satellite": [{"name": "SPARRSO", "url": "https://www.sparrso.gov.bd/"}],
        "news": ["thedailystar.net", "dhakatribune.com", "tbsnews.net", "unb.com.bd", "newagebd.net"],
    },
    "BR": {
        "government": [
            {"name": "IBAMA / Prevfogo", "url": "https://www.gov.br/ibama/pt-br/assuntos/fiscalizacao-e-protecao-ambiental/incendios-florestais"},
            {"name": "National Civil Defense", "url": "https://www.gov.br/mdr/pt-br/assuntos/protecao-e-defesa-civil"},
        ],
        "national_satellite": [{"name": "INPE Programa Queimadas", "url": "https://terrabrasilis.dpi.inpe.br/queimadas/portal/"}],
        "news": ["agenciabrasil.ebc.com.br", "reuters.com", "apnews.com", "riotimesonline.com", "mongabay.com"],
    },
    "IN": {
        "government": [
            {"name": "Forest Survey of India fire alerts", "url": "https://fsiforestfire.gov.in/"},
            {"name": "National Disaster Management Authority", "url": "https://ndma.gov.in/"},
        ],
        "national_satellite": [{"name": "ISRO Bhuvan fire products", "url": "https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php"}],
        "news": ["thehindu.com", "indianexpress.com", "hindustantimes.com", "timesofindia.indiatimes.com", "ndtv.com", "downtoearth.org.in"],
    },
    "ID": {
        "government": [
            {"name": "BNPB (National Disaster Management Agency)", "url": "https://bnpb.go.id/"},
            {"name": "SiPongi (Ministry of Environment and Forestry fire monitoring)", "url": "https://sipongi.menlhk.go.id/"},
        ],
        "national_satellite": [{"name": "BRIN hotspot products", "url": "https://hotspot.brin.go.id/"}],
        "news": ["thejakartapost.com", "en.antaranews.com", "jakartaglobe.id", "mongabay.com"],
    },
    "US": {
        "government": [
            {"name": "NIFC WFIGS incidents", "url": "https://data-nifc.opendata.arcgis.com/", "automated": "nifc"},
            {"name": "InciWeb", "url": "https://inciweb.wildfire.gov/"},
            {"name": "CAL FIRE incidents", "url": "https://www.fire.ca.gov/incidents"},
        ],
        "national_satellite": [{"name": "NOAA Hazard Mapping System", "url": "https://www.ospo.noaa.gov/products/land/hms.html"}],
        "news": ["apnews.com", "reuters.com", "npr.org", "latimes.com", "sfchronicle.com", "oregonlive.com"],
    },
    "CA": {
        "government": [
            {"name": "CIFFC national fire situation", "url": "https://ciffc.net/"},
            {"name": "Provincial wildfire services", "url": "https://cwfis.cfs.nrcan.gc.ca/interactive-map"},
        ],
        "national_satellite": [{"name": "CWFIS M3 fire perimeters", "url": "https://cwfis.cfs.nrcan.gc.ca/", "automated": "cwfis_m3"}],
        "news": ["cbc.ca", "ctvnews.ca", "globalnews.ca", "theglobeandmail.com"],
    },
    "AU": {
        "government": [
            {"name": "NSW Rural Fire Service major incidents", "url": "https://www.rfs.nsw.gov.au/fire-information/fires-near-me", "automated": "nsw_rfs"},
            {"name": "Emergency Management Victoria", "url": "https://emergency.vic.gov.au/"},
            {"name": "Queensland Fire Department", "url": "https://www.fire.qld.gov.au/"},
            {"name": "NAFC", "url": "https://www.nafc.org.au/"},
        ],
        "national_satellite": [{"name": "Geoscience Australia Digital Earth Australia Hotspots", "url": "https://hotspots.dea.ga.gov.au/"}],
        "news": ["abc.net.au", "sbs.com.au", "9news.com.au", "theguardian.com", "smh.com.au"],
    },
    "GR": {
        "government": [{"name": "Hellenic Fire Service", "url": "https://www.fireservice.gr/"}, {"name": "Civil Protection (civilprotection.gov.gr)", "url": "https://civilprotection.gov.gr/"}],
        "news": ["ekathimerini.com", "greekreporter.com", "keeptalkinggreece.com"],
    },
    "TR": {
        "government": [{"name": "General Directorate of Forestry (OGM)", "url": "https://www.ogm.gov.tr/"}, {"name": "AFAD", "url": "https://en.afad.gov.tr/"}],
        "news": ["dailysabah.com", "hurriyetdailynews.com", "aa.com.tr"],
    },
    "RU": {
        "government": [{"name": "Avialesookhrana (Aerial Forest Protection)", "url": "https://aviales.ru/"}],
        "national_satellite": [{"name": "ISDM-Rosleskhoz", "url": "https://public.aviales.ru/"}],
        "news": ["themoscowtimes.com", "tass.com"],
    },
    "MX": {
        "government": [{"name": "CONAFOR", "url": "https://www.gob.mx/conafor"}],
        "national_satellite": [{"name": "CONABIO fire alerts", "url": "http://incendios.conabio.gob.mx/"}],
        "news": ["mexiconewsdaily.com", "apnews.com", "reuters.com"],
    },
    "ZA": {
        "government": [{"name": "Working on Fire", "url": "https://www.workingonfire.org/"}],
        "national_satellite": [{"name": "AFIS (Advanced Fire Information System)", "url": "https://afis.co.za/"}],
        "news": ["news24.com", "iol.co.za", "timeslive.co.za"],
    },
    "PT": {
        "government": [{"name": "ANEPC (Civil Protection)", "url": "https://prociv.gov.pt/"}, {"name": "Fogos.pt", "url": "https://fogos.pt/"}],
        "news": ["portugalresident.com", "theportugalnews.com"],
    },
    "ES": {
        "government": [{"name": "MITECO wildfire statistics", "url": "https://www.miteco.gob.es/"}],
        "news": ["thelocal.es", "english.elpais.com", "surinenglish.com"],
    },
}

EU_EFFIS_COUNTRIES = {
    "AL", "AT", "BA", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "DZ", "EE", "EG", "ES", "FI", "FR", "GB", "GE", "GR", "HR", "HU", "IE", "IL",
    "IT", "LB", "LT", "LU", "LV", "LY", "MA", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SY", "TN", "TR", "UA", "XK",
}

FALLBACK_SOURCES: dict[str, Any] = {
    "government": [
        {"name": "National disaster management agency", "url": None},
        {"name": "Environment / forestry ministry", "url": None},
        {"name": "National fire service", "url": None},
    ],
    "national_satellite": [],
    "news": ["reuters.com", "apnews.com", "aljazeera.com", "bbc.com"],
}

WIRE_SERVICES = {"reuters.com", "apnews.com", "afp.com", "bbc.com", "bbc.co.uk", "aljazeera.com", "theguardian.com"}


def sources_for_country(code: str | None) -> dict[str, Any]:
    return COUNTRY_SOURCES.get((code or "").upper(), FALLBACK_SOURCES)


def source_reliability(domain: str, country_code: str | None) -> tuple[int, str]:
    domain = (domain or "").lower().removeprefix("www.")
    if domain.endswith(".gov") or ".gov." in domain or domain.endswith(".gob.mx") or domain.endswith(".go.id"):
        return 95, "government domain"
    if domain in WIRE_SERVICES:
        return 88, "international wire / public broadcaster"
    if domain in sources_for_country(country_code).get("news", []):
        return 82, "established national English-language outlet"
    return 60, "unrecognised outlet"
