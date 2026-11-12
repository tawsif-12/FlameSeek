import {
  BadgeCheck,
  CloudSun,
  Database,
  ExternalLink,
  Map,
  Newspaper,
  Satellite,
  ShieldCheck,
} from "lucide-react";
import "../data-sources.css";

type SourceGroup = "Fire observations" | "Observation context" | "Corroboration and incidents" | "Geography and evidence";

type ProjectDataSource = {
  name: string;
  description: string;
  dataType: string;
  organization: string;
  url: string;
  group: SourceGroup;
  optional?: boolean;
};

const DATA_SOURCES: ProjectDataSource[] = [
  {
    name: "MODIS Terra and Aqua Active Fire",
    description: "MOD14 and MYD14 thermal-anomaly observations used as FlameSeek's long-running, approximately 1 km active-fire record.",
    dataType: "Satellite active-fire detections",
    organization: "NASA GSFC / NASA FIRMS",
    url: "https://modis.gsfc.nasa.gov/data/dataprod/mod14.php",
    group: "Fire observations",
  },
  {
    name: "VIIRS S-NPP Active Fire",
    description: "VNP14IMG 375 m observations that add finer spatial detail and sensitivity to smaller thermal signals.",
    dataType: "Satellite active-fire detections",
    organization: "NASA GSFC / NASA FIRMS",
    url: "https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html",
    group: "Fire observations",
  },
  {
    name: "VIIRS NOAA-20 Active Fire",
    description: "VJ114IMG 375 m observations used for current monitoring, event construction and cross-sensor checks.",
    dataType: "Satellite active-fire detections",
    organization: "NASA GSFC / NASA FIRMS",
    url: "https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html",
    group: "Fire observations",
  },
  {
    name: "VIIRS NOAA-21 Active Fire",
    description: "VJ214IMG-family 375 m observations used by the current-fire stream; the configured historical archive does not claim NOAA-21 coverage.",
    dataType: "Near Real-Time active-fire detections",
    organization: "NASA GSFC / NASA FIRMS",
    url: "https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html",
    group: "Fire observations",
  },
  {
    name: "GOES-East and GOES-West Fire",
    description: "Frequent geostationary active-fire detections used as regional corroboration and timing context across the Americas.",
    dataType: "Geostationary fire detections",
    organization: "NOAA / NASA FIRMS",
    url: "https://firms.modaps.eosdis.nasa.gov/",
    group: "Fire observations",
  },
  {
    name: "Landsat 8 and 9 Active Fire",
    description: "Higher-resolution active-fire and thermal-anomaly detections used as supporting evidence where FIRMS coverage is available.",
    dataType: "30 m satellite fire detections",
    organization: "NASA / USGS via NASA FIRMS",
    url: "https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_Landsat_Firehotspots.html",
    group: "Fire observations",
  },
  {
    name: "NASA FIRMS Data Availability",
    description: "Per-source archive date ranges used to distinguish unavailable observations from valid periods with no detections.",
    dataType: "Archive availability metadata",
    organization: "NASA EOSDIS FIRMS",
    url: "https://firms.modaps.eosdis.nasa.gov/api/data_availability/",
    group: "Observation context",
  },
  {
    name: "CelesTrak Orbital Elements",
    description: "Current orbital elements for Terra, Aqua, S-NPP, NOAA-20 and NOAA-21 used to predict passes and expected swath coverage.",
    dataType: "Two-line orbital elements",
    organization: "CelesTrak",
    url: "https://celestrak.org/",
    group: "Observation context",
  },
  {
    name: "Open-Meteo Historical and Forecast Weather",
    description: "Cloud cover, wind, humidity and temperature used for observation-quality context, historical analogues and forecasts.",
    dataType: "Weather reanalysis and forecast",
    organization: "Open-Meteo",
    url: "https://open-meteo.com/en/docs/historical-weather-api",
    group: "Observation context",
  },
  {
    name: "Open-Meteo Elevation",
    description: "Copernicus DEM-derived elevation values used to provide terrain and slope-direction context for forecast features.",
    dataType: "Digital elevation data",
    organization: "Open-Meteo / Copernicus",
    url: "https://open-meteo.com/en/docs/elevation-api",
    group: "Observation context",
  },
  {
    name: "Sentinel-2 Level-2A Scene Metadata",
    description: "Scene availability, acquisition details and cloud cover used to locate imagery for smoke and burn-scar review.",
    dataType: "Satellite scene metadata",
    organization: "ESA Copernicus / Element 84 Earth Search",
    url: "https://earth-search.aws.element84.com/v1",
    group: "Corroboration and incidents",
  },
  {
    name: "EFFIS Burnt Areas",
    description: "Mapped burnt-area records used as regional corroboration across Europe, the Middle East and North Africa.",
    dataType: "Mapped burnt-area polygons",
    organization: "European Commission / Copernicus EMS",
    url: "https://effis.jrc.ec.europa.eu/",
    group: "Corroboration and incidents",
  },
  {
    name: "CWFIS M3 Fire Perimeters",
    description: "Canadian satellite-derived fire perimeters used to corroborate Fire Cases within Canada.",
    dataType: "Fire-perimeter geospatial data",
    organization: "Natural Resources Canada",
    url: "https://cwfis.cfs.nrcan.gc.ca/",
    group: "Corroboration and incidents",
  },
  {
    name: "GDACS Wildfire Alerts",
    description: "Global disaster alerts used as independent official-event evidence for large wildfire events.",
    dataType: "Official disaster alerts",
    organization: "United Nations / European Commission",
    url: "https://www.gdacs.org/",
    group: "Corroboration and incidents",
  },
  {
    name: "NIFC WFIGS Incident Locations",
    description: "Current United States wildland-fire incident locations, including prescribed-fire classifications when supplied.",
    dataType: "Official incident locations",
    organization: "U.S. National Interagency Fire Center",
    url: "https://data-nifc.opendata.arcgis.com/",
    group: "Corroboration and incidents",
  },
  {
    name: "NSW Rural Fire Service Major Incidents",
    description: "Major-incident and hazard-reduction information used as official regional evidence in New South Wales.",
    dataType: "Official incident feed",
    organization: "NSW Rural Fire Service",
    url: "https://www.rfs.nsw.gov.au/fire-information/fires-near-me",
    group: "Corroboration and incidents",
  },
  {
    name: "GDELT DOC 2.0",
    description: "Global English-language news results queried by place and event time for transparent Fire Case evidence matching.",
    dataType: "News event records",
    organization: "The GDELT Project",
    url: "https://www.gdeltproject.org/",
    group: "Geography and evidence",
  },
  {
    name: "NewsAPI",
    description: "Additional event- and location-based news articles used only when a NewsAPI credential is configured.",
    dataType: "News article metadata",
    organization: "NewsAPI",
    url: "https://newsapi.org/",
    group: "Geography and evidence",
    optional: true,
  },
  {
    name: "OpenStreetMap Nominatim",
    description: "Place search and reverse geocoding used for location selection and administrative geographic context.",
    dataType: "Geocoding and place data",
    organization: "OpenStreetMap Foundation / Nominatim",
    url: "https://nominatim.org/",
    group: "Geography and evidence",
  },
  {
    name: "OpenStreetMap Overpass",
    description: "Mapped forests, protected areas, known heat sources, roads, facilities and farmland used for context and exposure analysis.",
    dataType: "Open geospatial features",
    organization: "OpenStreetMap contributors / Overpass",
    url: "https://overpass-api.de/",
    group: "Geography and evidence",
  },
  {
    name: "WorldPop Population Data",
    description: "Modelled population estimates used to summarize people located inside an issued forecast corridor.",
    dataType: "Gridded population estimates",
    organization: "WorldPop, University of Southampton",
    url: "https://www.worldpop.org/",
    group: "Geography and evidence",
  },
];

const GROUPS: Array<{ name: SourceGroup; description: string; icon: typeof Satellite }> = [
  { name: "Fire observations", description: "Primary and supporting satellite measurements of active fire and thermal anomalies.", icon: Satellite },
  { name: "Observation context", description: "Sources that describe satellite availability, expected coverage, weather and terrain.", icon: CloudSun },
  { name: "Corroboration and incidents", description: "Independent satellite products and official records used to check fire events.", icon: ShieldCheck },
  { name: "Geography and evidence", description: "Place, exposure and news sources used to interpret observed fire activity.", icon: Map },
];

function DataSourceCard({ source }: { source: ProjectDataSource }) {
  return (
    <article className="ds-card">
      <div className="ds-card-topline">
        <span className="ds-status"><BadgeCheck size={14} aria-hidden="true" />{source.optional ? "Optional integration" : "Implemented"}</span>
        <Database size={18} aria-hidden="true" />
      </div>
      <h3>{source.name}</h3>
      <p>{source.description}</p>
      <dl>
        <div><dt>Data type</dt><dd>{source.dataType}</dd></div>
        <div><dt>Source</dt><dd>{source.organization}</dd></div>
      </dl>
      <a href={source.url} target="_blank" rel="noreferrer" aria-label={`Visit the official source for ${source.name}`}>
        Visit official source <ExternalLink size={15} aria-hidden="true" />
      </a>
    </article>
  );
}

export default function DataSourcesPage() {
  return (
    <main className="content-page space-shell space-page ds-page">
      <header className="ds-hero">
        <div className="ds-hero-copy">
          <p className="ds-eyebrow"><Database size={14} aria-hidden="true" />Verified project sources</p>
          <h1>Data Sources</h1>
          <p>The satellite, environmental, geographic and evidence datasets implemented in FlameSeek. Every link opens the source organization's official website.</p>
        </div>
        <div className="ds-hero-summary" aria-label="Dataset summary">
          <strong>{DATA_SOURCES.length}</strong>
          <span>implemented source integrations</span>
          <small>Primary observations, context and corroboration</small>
        </div>
      </header>

      <nav className="ds-index" aria-label="Data source categories">
        {GROUPS.map(({ name, icon: Icon }) => (
          <a href={`#${name.toLowerCase().replace(/\s+/g, "-")}`} key={name}><Icon size={15} aria-hidden="true" />{name}</a>
        ))}
      </nav>

      {GROUPS.map(({ name, description, icon: Icon }) => {
        const sources = DATA_SOURCES.filter((source) => source.group === name);
        return (
          <section className="ds-group" id={name.toLowerCase().replace(/\s+/g, "-")} key={name}>
            <header className="ds-group-header">
              <span><Icon size={21} aria-hidden="true" /></span>
              <div><h2>{name}</h2><p>{description}</p></div>
              <b>{sources.length} sources</b>
            </header>
            <div className="ds-grid">{sources.map((source) => <DataSourceCard source={source} key={source.name} />)}</div>
          </section>
        );
      })}

      <aside className="ds-note">
        <Newspaper size={19} aria-hidden="true" />
        <p><strong>Scope note.</strong> Manual-review websites are not listed as integrated datasets. NewsAPI is shown separately because the code uses it only when its API key is configured.</p>
      </aside>
    </main>
  );
}
