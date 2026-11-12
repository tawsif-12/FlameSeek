import { useEffect, useState } from "react";
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
  review?: boolean;
};

const DATA_SOURCES: ProjectDataSource[] = [
  { name: "NASA FIRMS Download Archive", description: "Find and download MODIS and VIIRS active-fire observations from the provider. Some archive requests require a free Earthdata account.", dataType: "Original satellite datasets", organization: "NASA EOSDIS FIRMS", url: "https://firms.modaps.eosdis.nasa.gov/download/", group: "Fire observations" },
  { name: "Himawari Imagery", description: "Explore Asia-Pacific geostationary imagery for visual review. Project Himawari analysis CSVs are available in the download catalog below.", dataType: "Imagery viewer", organization: "RAMMB / CIRA", url: "https://rammb-slider.cira.colostate.edu/", group: "Corroboration and incidents", review: true },
  { name: "Meteosat Imagery", description: "Explore Europe and Africa satellite imagery for visual review.", dataType: "Imagery viewer", organization: "EUMETSAT", url: "https://view.eumetsat.int/", group: "Corroboration and incidents", review: true },
  { name: "NASA Worldview", description: "Browse satellite imagery, thermal anomalies and smoke context by date and location.", dataType: "Satellite imagery viewer", organization: "NASA EOSDIS", url: "https://worldview.earthdata.nasa.gov/", group: "Corroboration and incidents", review: true },
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
        <span className="ds-status"><BadgeCheck size={14} aria-hidden="true" />{source.review ? "Visual review" : source.optional ? "Optional integration" : "Data access"}</span>
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

type Dataset = { path: string; name: string; collection: string; bytes: number; columns: string[]; has_rows: boolean; modified: string };
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
function DatasetCatalog() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("");
  const [status, setStatus] = useState("Loading datasets…");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus("Loading datasets…");
    fetch(`${API_BASE}/api/datasets`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(data => { setDatasets(data.datasets); setStatus(""); })
      .catch(() => { if (!controller.signal.aborted) setStatus("Dataset catalog is unavailable. Please try again."); });
    return () => controller.abort();
  }, [attempt]);
  const filtered = datasets.filter(item => (!collection || item.collection === collection) &&
    `${item.name} ${item.path} ${item.collection} ${item.columns.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="ds-group" id="project-datasets">
    <header className="ds-group-header"><span><Database size={21} /></span><div><h2>Project dataset downloads</h2><p>Original satellite input CSVs and generated scientific tables. Download the files used in this project.</p></div><b>{datasets.length} files</b></header>
    <div className="ds-catalog-controls">
      <label>Search datasets<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Try MODIS, VIIRS, Himawari, FRE…" /></label>
      <label>Collection<select value={collection} onChange={event => setCollection(event.target.value)}><option value="">All collections</option>{[...new Set(datasets.map(item => item.collection))].map(name => <option key={name}>{name}</option>)}</select></label>
    </div>
    {status ? <p role="status">{status} {status.includes("unavailable") && <button onClick={() => setAttempt(value => value + 1)}>Retry</button>}</p> : <p role="status">Showing {filtered.length} of {datasets.length} datasets</p>}
    <div className="ds-grid">{filtered.map(item => <article className="ds-card" key={item.path}>
      <div className="ds-card-topline"><span className="ds-status">CSV · {item.bytes < 1024 ? `${item.bytes} B` : item.bytes < 1048576 ? `${(item.bytes / 1024).toFixed(1)} KB` : `${(item.bytes / 1048576).toFixed(1)} MB`}</span><Database size={18} /></div>
      <h3>{item.name.replace(/\.csv$/i, "").replace(/_/g, " ")}</h3><p>{item.collection}</p><code className="ds-file-path">{item.path}</code>
      {!item.has_rows && <p className="ds-empty-file">Header only — no data rows are currently available.</p>}
      <dl><div><dt>Updated</dt><dd>{new Date(item.modified).toLocaleDateString()}</dd></div><div><dt>Columns</dt><dd>{item.columns.length}</dd></div></dl>
      <details><summary>View column names</summary><p className="ds-file-path">{item.columns.join(", ")}</p></details>
      <a href={`${API_BASE}/api/datasets/download/${item.path.split("/").map(encodeURIComponent).join("/")}`} download={item.name} aria-label={`Download ${item.path}`}>Download CSV <ExternalLink size={15} aria-hidden="true" /></a>
    </article>)}</div>
    {!status && filtered.length === 0 && <p>No datasets match your search. Try another name or collection.</p>}
  </section>;
}

export default function DataSourcesPage() {
  return (
    <main className="content-page space-shell space-page ds-page">
      <header className="ds-hero">
        <div className="ds-hero-copy">
          <p className="ds-eyebrow"><Database size={14} aria-hidden="true" />Verified project sources</p>
          <h1>Data Sources</h1>
          <p>Download the project's satellite CSVs and analysis tables, or explore the original satellite, environmental, geographic and evidence data providers.</p>
        </div>
        <div className="ds-hero-summary" aria-label="Dataset summary">
          <strong>{DATA_SOURCES.length}</strong>
          <span>data providers and access links</span>
          <small>Primary observations, context and corroboration</small>
        </div>
      </header>

      <nav className="ds-index" aria-label="Data source categories">
        <a href="#project-datasets"><Database size={15} aria-hidden="true" />Download datasets</a>
        {GROUPS.map(({ name, icon: Icon }) => (
          <a href={`#${name.toLowerCase().replace(/\s+/g, "-")}`} key={name}><Icon size={15} aria-hidden="true" />{name}</a>
        ))}
      </nav>

      <DatasetCatalog />

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
        <p><strong>About these datasets.</strong> Satellite input CSVs are original observations; analysis and diagnostic CSVs are project-generated outputs. A header-only file contains no observations. Provider links may require an account or API key. Imagery viewers are labelled for visual review; NewsAPI requires a configured API key.</p>
      </aside>
    </main>
  );
}
