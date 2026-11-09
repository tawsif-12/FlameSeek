import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "react-plotly.js";
import { GeoJSON, MapContainer, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { getHotspotsInBox, normalizeApiError, runJob, startFireMemory, startPlacePipeline, savedFireMemory, savedPlacePipeline } from "../api/client";
import { aoiBBox, aoiContains, describeAoi, useAppContext } from "../context/AppContext";
import type { FireMemoryResult, HotspotRecord, Job, PlacePipelineSummary, SensorName } from "../types/api";
import { StatusPill } from "../components/HarmonizedProvenance";
import DataCoverageNotice from "../components/DataCoverageNotice";
import "../harmonized.css";
import { featureHref } from '../api/locationRoutes';

/* "<Place> Fire Intelligence": one page answering the eight area questions from the area's own
   records. The first answers come from Fire Memory (fast, Aqua 13:30-equivalent counts); once the
   FlameSeek pipeline has processed the place (footprints, events, energy-conserving grid), the history,
   hotspot, season, change, unusual and risk answers switch to it. Every answer names its source and status. */

type PlotProps = React.ComponentProps<typeof Plot>;
const RAMP = ["#8f3a14", "#d4561f", "#ff8a4c", "#ffc78a"]; // dark-surface ordinal ramp (validated)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LAYOUT: PlotProps["layout"] = {
  paper_bgcolor: "transparent", plot_bgcolor: "transparent", autosize: true, showlegend: false,
  font: { color: "#c6dcf6", family: "Space Grotesk, Inter, sans-serif", size: 12 },
  margin: { t: 26, r: 16, b: 36, l: 48 },
  xaxis: { gridcolor: "rgba(0,0,0,0)", color: "#94a3b8" },
  yaxis: { gridcolor: "rgba(148,197,255,0.12)", color: "#94a3b8", zeroline: false },
  hoverlabel: { bgcolor: "#0a1220", bordercolor: "#6ad7ff", font: { color: "#e6f1ff" } },
};
const CONFIG = { displayModeBar: false, responsive: true };
/* Staged loading: live hotspots (seconds) -> 12-month quick look (about a minute the first time) ->
   full history (background). MODIS + Suomi-NPP only: NOAA-20/21 repeat what S-NPP sees and would add
   about a third more NASA requests without changing the long-term record. Results are cached on disk. */
const HUB_SENSORS: SensorName[] = ["modis", "viirs_snpp"];
const QUICK_YEARS = 1;

function kmPerDeg(lat: number) { return { x: 111.32 * Math.cos((lat * Math.PI) / 180), y: 110.57 }; }
function boxArea(b: [number, number, number, number]) {
  const k = kmPerDeg((b[1] + b[3]) / 2);
  return Math.max((b[2] - b[0]) * k.x * (b[3] - b[1]) * k.y, 1);
}

function FitBox({ box }: { box: [number, number, number, number] }) {
  const map = useMap();
  useEffect(() => { map.fitBounds([[box[1], box[0]], [box[3], box[2]]] as LatLngBoundsExpression, { padding: [16, 16], animate: false }); }, [box, map]);
  return null;
}

function Q({ n, q, children, source, status }: { n: number; q: string; children: React.ReactNode; source?: string; status?: string }) {
  return (
    <article className="glass-card hz-q">
      <div className="hz-q-head"><span className="method-index" aria-hidden="true">{String(n).padStart(2, "0")}</span><h4>{q}</h4>{status && <StatusPill status={status} />}</div>
      <div className="hz-q-body">{children}</div>
      {source && <p className="hz-src">Source: {source}</p>}
    </article>
  );
}

export default function AreaIntelligencePage() {
  const { aoi, lockedArea, setMemory: shareMemory } = useAppContext();
  const [years, setYears] = useState(5);
  const [quick, setQuick] = useState<FireMemoryResult | null>(null);
  const [full, setFull] = useState<FireMemoryResult | null>(null);
  const [quickJob, setQuickJob] = useState<Job<FireMemoryResult> | null>(null);
  const [fullJob, setFullJob] = useState<Job<FireMemoryResult> | null>(null);
  const [quickError, setQuickError] = useState<string | null>(null);
  const [fullError, setFullError] = useState<string | null>(null);
  const [live, setLive] = useState<HotspotRecord[] | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [pipe, setPipe] = useState<PlacePipelineSummary | null>(null);
  const [pipeJob, setPipeJob] = useState<Job<PlacePipelineSummary> | null>(null);
  const [pipeError, setPipeError] = useState<string | null>(null);
  const runRef = useRef(0);

  const box = useMemo(() => (aoi ? aoiBBox(aoi) : null), [aoi]);
  const ring = useMemo((): [number, number, number, number] | null => {
    if (!box) return null;
    const dx = box[2] - box[0], dy = box[3] - box[1];
    return [Math.max(box[0] - dx, -180), Math.max(box[1] - dy, -90), Math.min(box[2] + dx, 180), Math.min(box[3] + dy, 90)];
  }, [box]);
  const name = aoi ? describeAoi(aoi) : "";
  const [title, subtitle] = useMemo(() => {
    const parts = name.split(",").map((x) => x.trim()).filter(Boolean);
    return [parts[0] ?? name, parts.slice(1).join(", ")];
  }, [name]);

  // Stage 2 (quick look, last 12 months), then stage 3 (full history). Both are Fire Memory jobs:
  // identical requests share one backend job, and downloaded chunks are cached and reused.
  useEffect(() => {
    if (!aoi) return;
    const id = ++runRef.current;
    const mine = () => id === runRef.current;
    setQuick(null); setFull(null); setQuickError(null); setFullError(null); setQuickJob(null); setFullJob(null);
    setPipe(null); setPipeJob(null); setPipeError(null);
    // Show exact-query saved results before waiting on fresh NASA downloads.
    savedFireMemory(aoi, years, HUB_SENSORS).then((saved) => {
      if (saved && mine()) setFull((current) => current && !current.provenance?.saved_preview ? current : saved);
    }).catch(() => {});
    savedPlacePipeline(aoi, years).then((saved) => {
      if (saved && mine()) setPipe((current) => current && !current.provenance?.saved_preview ? current : saved);
    }).catch(() => {});
    (async () => {
      try {
        const q = await runJob(startFireMemory(aoi, QUICK_YEARS, HUB_SENSORS, 30), (j) => mine() && setQuickJob(j));
        if (mine()) setQuick(q);
      } catch (e) {
        if (mine()) setQuickError(normalizeApiError(e));
      }
      if (!mine()) return;
      // Stage 4 runs alongside stage 3: both use the same NASA downloads (shared in flight and cached).
      runJob(startPlacePipeline(aoi, years), (j) => mine() && setPipeJob(j))
        .then((r) => mine() && setPipe(r))
        .catch((e) => mine() && setPipeError(normalizeApiError(e)));
      try {
        const f = await runJob(startFireMemory(aoi, years, HUB_SENSORS, 30), (j) => mine() && setFullJob(j));
        if (mine()) { setFull(f); shareMemory(f); }
      } catch (e) {
        if (mine()) setFullError(normalizeApiError(e));
      }
    })();
    return () => { ++runRef.current; };
  }, [aoi, years]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live FIRMS hotspots in and around the place (last 24 hours; cut from the shared worldwide download when fresh).
  useEffect(() => {
    if (!ring) return;
    setLive(null); setLiveError(null);
    getHotspotsInBox(ring, 1).then((r) => setLive(r.hotspots)).catch((e) => setLiveError(normalizeApiError(e)));
  }, [ring]);

  const neighbours = useMemo(() => {
    if (!aoi || !box || !ring || !live) return null;
    const inside = live.filter((h) => aoiContains(aoi, h.lat, h.lon));
    const ringOnly = live.filter((h) => !(h.lon >= box[0] && h.lon <= box[2] && h.lat >= box[1] && h.lat <= box[3]));
    const aIn = boxArea(box), aRing = boxArea(ring) - aIn;
    const dIn = (inside.length / aIn) * 1000, dRing = (ringOnly.length / aRing) * 1000;
    return { inside, ringOnly, dIn, dRing, ratio: dRing > 0 ? dIn / dRing : null, latest: inside.map((h) => h.acq_datetime).sort().slice(-1)[0] };
  }, [aoi, box, ring, live]);

  const history = full;
  const memory = full ?? quick;
  const isQuick = !full && !!quick;
  const annual = useMemo(() => {
    if (!history) return [];
    const byYear = new Map<number, { activity: number; hotspots: number; months: number }>();
    history.monthly.forEach((m) => {
      const y = byYear.get(m.year) ?? { activity: 0, hotspots: 0, months: 0 };
      y.activity += m.harmonized_activity; y.hotspots += m.hotspot_count; y.months += 1;
      byYear.set(m.year, y);
    });
    return [...byYear.entries()].sort((a, b) => a[0] - b[0]).map(([year, v]) => ({ year, ...v }));
  }, [history]);
  const pipeFull = pipe ? pipe.yearly.filter((y) => y.full_year) : [];
  const fullYears = pipe ? pipeFull : annual.filter((y) => y.months === 12);
  const fireYears = pipe ? pipeFull.filter((y) => y.n_events > 0).length : annual.filter((y) => y.months === 12 && y.hotspots > 0).length;

  type Cell = { lat: number; lon: number; days: number; years: number; first: string; last: string; detail: string };
  const cellDeg = pipe ? pipe.hotspot_map.cell_deg : memory?.hotspot_map?.cell_deg ?? 0.1;
  const cells: Cell[] = useMemo(() => pipe
    ? pipe.hotspot_map.cells.map((c) => ({ ...c, detail: `peak fire power ${c.frp_max_mw.toFixed(1)} MW` }))
    : (memory?.hotspot_map?.cells ?? []).map((c) => ({ ...c, detail: `${c.detections} detections` })), [pipe, memory]);
  const dayBreaks = useMemo(() => {
    const d = cells.map((c) => c.days).sort((a, b) => a - b);
    const q = (p: number) => d[Math.min(d.length - 1, Math.floor(p * d.length))] ?? 1;
    return Array.from(new Set([q(0.5), q(0.8), q(0.95)])).filter((b) => b < (d[d.length - 1] ?? 0)).slice(0, 3);
  }, [cells]);
  const cellClass = (days: number) => dayBreaks.filter((b) => days > b).length;
  const legendRanges = useMemo(() => {
    const max = cells.reduce((m, c) => Math.max(m, c.days), 0);
    const edges = [0, ...dayBreaks, max];
    return edges.slice(1).map((hi, i) => {
      const lo = edges[i] + 1;
      return lo >= hi ? `${hi}` : `${lo}–${hi}`;
    });
  }, [cells, dayBreaks]);

  if (!aoi || !box) {
    return (
      <main className="content-page space-shell space-page">
        <div className="space-hero-strip"><header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Area fire intelligence</p>
          <h2>Choose a place first</h2>
          <p className="lead">Search for a country, district, forest or protected area to see its fire history, current activity, seasons and risk.</p>
          <Link to="/search" className="oc-btn-primary hz-cta">Search a place →</Link>
        </header></div>
      </main>
    );
  }

  const cmp = history?.current_vs_historical;
  const risk = pipe ? pipe.area_risk : history?.area_risk;
  const season = memory?.seasonal_profile;
  const pSeason = pipe?.seasonal_profile;
  const histReady = !!pipe || !!history;
  const SRC = pipe ? `FlameSeek pipeline, ${pipe.period.start} to ${pipe.period.end}` : history ? `Fire Memory, ${history.period.start} to ${history.period.end} (pipeline still running)` : undefined;
  const quality = memory?.observation_quality;
  const loadingMemory = !memory && !quickError && !fullError;
  const memError = !memory ? (fullError ?? quickError) : null;
  const pct = (j: Job<FireMemoryResult> | null) => (j ? Math.round(j.progress * 100) : 0);
  const historyWait = fullError ? `History unavailable: ${fullError}` : `Loading the ${years}-year history: ${pct(fullJob)}%${/quota/i.test(fullJob?.message ?? "") ? " (paused for NASA's request limit, resumes automatically)" : ""}. The rest of the page is ready to read.`;
  const quickNote = isQuick ? " (last 12 months; full history still loading)" : "";
  const quotaWait = /quota/i.test(fullJob?.message ?? "");
  const pipePct = pipeJob ? Math.round(pipeJob.progress * 100) : 0;
  const pipeStatus = pipe?.provenance?.saved_preview ? `Saved through ${pipe.period.end}; ${pipeError ? `update unavailable: ${pipeError}` : `updating in background · ${pipePct}% · ${pipeJob?.message ?? "starting"}`}` : pipeError ? pipeError : pipe ? (pipe.served_from_cache ? "loaded from saved run" : `ready · ${pipe.quality.events} event${pipe.quality.events === 1 ? "" : "s"} from ${pipe.quality.clean_detections} detection${pipe.quality.clean_detections === 1 ? "" : "s"}`)
    : quick || quickError ? `${pipePct}% · ${pipeJob?.message ?? "starting"}` : "starts after the quick look";
  const historyStatus = quotaWait
    ? `${pct(fullJob)}% · paused: NASA allows 5,000 requests per 10 minutes, resumes automatically — keep reading meanwhile`
    : `${pct(fullJob)}% · ${fullJob?.message ?? "Preparing history"}. First-time downloads depend on NASA; completed runs are saved.`;

  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Area fire intelligence</p>
          <h2>{title} Fire Intelligence</h2>
          {subtitle && <p className="lead" style={{ marginBottom: 6 }}>{subtitle}</p>}
          <p className="lead">Fire history, current activity, seasons and risk for this place, from NASA satellite fire records. Answers appear as soon as their data is ready; each says where it comes from and how reliable it is.</p>
          <div className="hz-hero-actions" style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            <Link to="/search" className="hz-link-btn">← Change place</Link>
            <span className="hz-count">History:</span>
            <div className="hz-seg" role="group" style={{ minWidth: 240 }} title="Longer history takes longer the first time (NASA serves 5 days per request); downloads are saved and reused">
              {[5, 10, 20].map((y) => <button key={y} aria-pressed={years === y} onClick={() => setYears(y)}>{y} years</button>)}
            </div>
          </div>
          <ul className="hero-chips hz-provenance">
            <li><span className="dot" />Record: {memory ? `${memory.period.start} → ${memory.period.end}${isQuick ? " (quick look)" : ""}` : loadingMemory ? "loading…" : "awaiting data"}</li>
            <li><span className="dot" />Live: NASA FIRMS, last 24 hours</li>
            <li><span className="dot" />{pipe ? "Method: FlameSeek pipeline (fire events, energy-conserving grid)" : "Unit: Aqua 13:30-equivalent detections (harmonized)"}</li>
          </ul>
        </header>
      </div>

      <DataCoverageNotice start={pipe?.period.start ?? memory?.period.start} end={pipe?.period.end ?? memory?.period.end} />
      {!!pipe?.provenance?.failed_chunks && <p className="hz-honesty" role="alert">Incomplete download: {pipe.provenance.failed_chunks} archive requests failed. Missing dates are unknown; totals may undercount fires.</p>}
      {/* Loading steps: each answer appears as soon as its data is ready. */}
      <ol className="hz-steps" aria-label="Loading progress">
        <li className={live ? "done" : liveError ? "fail" : "active"}>
          <b>{live ? "✓" : liveError ? "!" : "…"}</b>
          <span><strong>Live hotspots</strong><small>{live ? `${neighbours?.inside.length ?? 0} in the last 24 hours` : liveError ? "unavailable" : "a few seconds"}</small></span>
        </li>
        <li className={quick ? "done" : quickError ? "fail" : "active"}>
          <b>{quick ? "✓" : quickError ? "!" : "…"}</b>
          <span><strong>Quick look: last 12 months</strong><small>{quick ? "ready" : quickError ? quickError : `${pct(quickJob)}% · ${quickJob?.message ?? "Checking saved data"}`}</small></span>
          {!quick && !quickError && <i className="hz-bar"><span style={{ width: `${pct(quickJob)}%` }} /></i>}
        </li>
        <li className={full ? "done" : fullError ? "fail" : quick || quickError ? "active" : "waiting"}>
          <b>{full ? "✓" : fullError ? "!" : quick || quickError ? "…" : "3"}</b>
          <span><strong>Full {years}-year history</strong><small>{full?.provenance?.saved_preview ? `Saved through ${full.period.end}; ${fullError ? `update unavailable: ${fullError}` : `updating in background · ${historyStatus}`}` : full ? (full.provenance?.served_from_cache ? "loaded from saved analysis" : "ready") : fullError ? fullError : quick || quickError ? historyStatus : "starts after the quick look"}</small></span>
          {!full && !fullError && (quick || quickError) && <i className="hz-bar"><span style={{ width: `${pct(fullJob)}%` }} /></i>}
        </li>
        <li className={pipe ? "done" : pipeError ? "fail" : quick || quickError ? "active" : "waiting"}>
          <b>{pipe ? "✓" : pipeError ? "!" : quick || quickError ? "…" : "4"}</b>
          <span><strong>FlameSeek pipeline: {years} years</strong><small>{pipeStatus}</small></span>
          {!pipe && !pipeError && (quick || quickError) && <i className="hz-bar"><span style={{ width: `${pipePct}%` }} /></i>}
        </li>
      </ol>
      {memError && <div className="hz-honesty" role="alert"><strong>Fire record unavailable</strong>{memError}</div>}

      {/* Four tiles, as in the concept */}
      <section className="hz-tiles hz-tiles-4">
        <a href="#history" className="glass-card hz-tile hz-tile-link">
          <div className="hz-tile-label">FIRE HISTORY</div>
          <div className="hz-tile-value">{histReady ? `${fireYears} / ${fullYears.length}` : fullError ? "—" : `${pct(fullJob)}%`}</div>
          <div className="hz-tile-label">{pipe ? "full years with fire events" : history ? "full years with fire detections" : "history loading"}</div>
        </a>
        <a href="#current" className="glass-card hz-tile hz-tile-link">
          <div className="hz-tile-label">CURRENT ACTIVITY</div>
          <div className="hz-tile-value">{neighbours ? neighbours.inside.length.toLocaleString() : liveError ? "—" : "…"}</div>
          <div className="hz-tile-label">hotspots in the last 24 hours</div>
        </a>
        <a href="#seasons" className="glass-card hz-tile hz-tile-link">
          <div className="hz-tile-label">SEASONAL PATTERNS</div>
          <div className="hz-tile-value">{pSeason ? (pSeason.peak_months.length ? pSeason.peak_months.join(", ") : "none") : season?.peak_months?.length ? season.peak_months.join(", ") : memory ? "none" : "…"}</div>
          <div className="hz-tile-label">high-activity months{!pipe && isQuick ? " (last 12 months)" : ""}</div>
        </a>
        <a href="#risk" className="glass-card hz-tile hz-tile-link">
          <div className="hz-tile-label">FUTURE RISK</div>
          <div className="hz-tile-value">{risk?.status === "computed" && risk.probability != null ? `${Math.round(risk.probability * 100)}%` : risk ? "withheld" : fullError ? "—" : `${pct(fullJob)}%`}</div>
          <div className="hz-tile-label">{risk?.window ? `chance of fire, next ${risk.window.days} days` : history && years < 10 ? "needs 10 years of history" : "modelled probability"}</div>
        </a>
      </section>

      <section className="hz-qgrid">
        <div id="history" />
        <Q n={1} q="Has this area experienced repeated fire activity?" status={histReady ? "computed" : loadingMemory ? "loading" : "awaiting data"} source={SRC}>
          {pipe ? (
            <p>The pipeline found <b>{pipe.quality.events}</b> separate fire event{pipe.quality.events === 1 ? "" : "s"} ({pipe.quality.clean_detections.toLocaleString()} satellite detection{pipe.quality.clean_detections === 1 ? "" : "s"}) and fire in <b>{fireYears} of {fullYears.length}</b> complete years.
              {" "}{fireYears >= Math.max(3, fullYears.length * 0.6) ? "Fire here is a repeated, regular occurrence." : fireYears > 0 ? "Fire here is occasional rather than every year." : "Fire is rare here."}</p>
          ) : history ? (
            <p>Satellites detected fire in <b>{fireYears} of {fullYears.length}</b> complete years ({history.summary.total_hotspots.toLocaleString()} hotspots in total).
              {" "}{history.critical_periods.length > 0 ? <>There were <b>{history.critical_periods.length}</b> periods with unusually many fires.</> : "No unusually intense periods were found."}
              {" "}{fireYears >= Math.max(3, fullYears.length * 0.6) ? "Fire here is a repeated, regular occurrence." : fireYears > 0 ? "Fire here is occasional rather than every year." : "Fire is rare here."}</p>
          ) : <p>{historyWait}</p>}
        </Q>

        <Q n={2} q="Where are the most frequently detected hotspots?" status={pipe ? "computed" : memory?.hotspot_map?.status ?? (memory ? "awaiting data (re-run analysis)" : loadingMemory ? "loading" : "awaiting data")}
          source={pipe ? `${pipe.hotspot_map.method}; FlameSeek pipeline` : memory?.hotspot_map ? `${memory.hotspot_map.method}${quickNote}` : undefined}>
          <div className="hz-mini-map">
            <MapContainer center={[(box[1] + box[3]) / 2, (box[0] + box[2]) / 2]} zoom={8} preferCanvas scrollWheelZoom={false}>
              <TileLayer attribution="Tiles &copy; Esri" url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
              <TileLayer attribution="Labels &copy; Esri" url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" />
              <FitBox box={box} />
              {aoi.geometry && <GeoJSON data={{ type: "Feature", geometry: aoi.geometry as GeoJSON.Geometry, properties: {} } as GeoJSON.Feature} interactive={false} style={{ color: "#6ad7ff", weight: 2, dashArray: "6 5", fill: false }} />}
              {cells.map((c) => {
                const h = cellDeg / 2;
                return (
                  <Rectangle key={`${c.lon},${c.lat}`} bounds={[[c.lat - h, c.lon - h], [c.lat + h, c.lon + h]]}
                    pathOptions={{ color: RAMP[cellClass(c.days)], weight: 1, fillColor: RAMP[cellClass(c.days)], fillOpacity: 0.85 }}>
                    <Tooltip>{c.days} days with fire · {c.years} years · {c.detail}<br />{c.first} → {c.last}</Tooltip>
                  </Rectangle>
                );
              })}
            </MapContainer>
          </div>
          {(pipe || memory?.hotspot_map) && (
            <>
              <div className="hz-legend" style={{ gridTemplateColumns: "repeat(2, auto)", marginTop: 8 }}>
                {cells.length === 0 ? <span>No fire detections in this period.</span> : legendRanges.map((l, i) =>
                  <span key={i}><span className="hz-sw" style={{ background: RAMP[i] }} />{l} day{l === "1" ? "" : "s"} with fire</span>)}
              </div>
              <ol className="hz-list" style={{ marginTop: 8 }}>
                {cells.slice(0, 5).map((c) => <li key={`${c.lon},${c.lat}`}>{c.lat.toFixed(2)}°, {c.lon.toFixed(2)}° — fire on <b>{c.days}</b> day{c.days === 1 ? "" : "s"} across <b>{c.years}</b> year{c.years === 1 ? "" : "s"}</li>)}
              </ol>
            </>
          )}
        </Q>

        <div id="current" />
        <Q n={3} q="Are neighbouring places experiencing similar fire activity?" status={neighbours ? "computed" : liveError ? "awaiting data" : "loading"}
          source="NASA FIRMS near-real-time hotspots, last 24 hours; neighbourhood = a ring one place-width wide around the place">
          {neighbours ? (
            <>
              <p>In the last 24 hours: <b>{neighbours.dIn.toFixed(2)}</b> hotspots per 1,000 km² inside {title}, against <b>{neighbours.dRing.toFixed(2)}</b> in the surrounding area.
                {" "}{neighbours.ratio == null ? "There was no fire around it." : neighbours.ratio > 1.5 ? "This place is more active than its neighbours." : neighbours.ratio < 0.67 ? "Its neighbours are more active than this place." : "Activity is similar to its neighbours."}</p>
              <p className="hz-src">{neighbours.inside.length} hotspots inside, {neighbours.ringOnly.length} in the surrounding area{neighbours.latest ? `; latest inside ${neighbours.latest}` : ""}. Live counts include unharmonized MODIS and VIIRS detections.</p>
            </>
          ) : <p>{liveError ? `Live data unavailable: ${liveError}` : "Loading live hotspots…"}</p>}
        </Q>

        <div id="seasons" />
        <Q n={4} q="Does fire activity increase during particular seasons?" status={pSeason || season ? "computed" : loadingMemory ? "loading" : "awaiting data"} source={pSeason ? `FlameSeek pipeline: ${pSeason.basis}` : season?.note}>
          {pSeason ? (
            <>
              <p>{pSeason.peak_months.length ? <>Fire events peak in <b>{pSeason.peak_months.join(", ")}</b>.</> : "There is no clear fire season."}
                {pSeason.quiet_months.length && pSeason.quiet_months.length < 12 ? <> Quietest: {pSeason.quiet_months.join(", ")}.</> : null}</p>
              {pSeason.months.every((m) => !m.mean_events) ? <p className="hz-src">No fire events in any month of the record, so there is no seasonal curve to draw.</p> : <div style={{ height: 220 }}>
                <Plot config={CONFIG} style={{ width: "100%", height: "100%" }} layout={{ ...LAYOUT, yaxis: { ...LAYOUT.yaxis, title: { text: "fire events per month" } } }}
                  data={[{ type: "bar", x: pSeason.months.map((m) => m.name), y: pSeason.months.map((m) => m.mean_events),
                    marker: { color: pSeason.months.map((m) => (pSeason.peak_months.includes(m.name) ? "#ff8a4c" : "#3987e5")) },
                    customdata: pSeason.months.map((m) => [m.median_events, m.years]),
                    hovertemplate: "%{x}: %{y:.2f} events on average<br>median %{customdata[0]} · %{customdata[1]} years<extra></extra>" }]} />
              </div>}
              <p className="hz-src">Bars: average fire events per month over {pSeason.full_years.length} complete year(s). Orange: peak months.</p>
            </>
          ) : season ? (
            <>
              <p>{season.peak_months.length ? <>Fire peaks in <b>{season.peak_months.join(", ")}</b>.</> : "There is no clear fire season."}
                {season.quiet_months.length ? <> Quietest: {season.quiet_months.join(", ")}.</> : null}</p>
              {season.months.every((m) => !m.median_activity) ? <p className="hz-src">No month had fire activity in a typical year, so there is no seasonal curve to draw.</p> : <div style={{ height: 220 }}>
                <Plot config={CONFIG} style={{ width: "100%", height: "100%" }} layout={{ ...LAYOUT, yaxis: { ...LAYOUT.yaxis, title: { text: "median activity" } } }}
                  data={[{ type: "bar", x: season.months.map((m) => MONTHS[m.month - 1]), y: season.months.map((m) => m.median_activity ?? 0),
                    marker: { color: season.months.map((m) => (season.peak_months.includes(m.name) || season.peak_months.includes(MONTHS[m.month - 1]) ? "#ff8a4c" : "#3987e5")) },
                    hovertemplate: "%{x}: %{y:.2f} median monthly activity<extra></extra>" }]} />
              </div>}
              <p className="hz-src">Orange bars: peak months. Median over {season.years.length} year(s) of the harmonized record{quickNote}.</p>
            </>
          ) : <p>{loadingMemory ? "Building the record…" : "awaiting data"}</p>}
        </Q>

        <Q n={5} q={`How has the fire pattern changed over ${years} years?`} status={pipe ? pipe.change.status : history?.change_points.status ?? (fullError ? "awaiting data" : "loading")} source={pipe ? pipe.change.method : history?.change_points.method}>
          {pipe ? (
            <>
              {pipe.yearly.every((y) => !y.n_events) ? <p className="hz-src">No fire events in any year of the record.</p> : <div style={{ height: 220 }}>
                <Plot config={CONFIG} style={{ width: "100%", height: "100%" }} layout={{ ...LAYOUT, yaxis: { ...LAYOUT.yaxis, title: { text: "fire events" } } }}
                  data={[{ type: "bar", x: pipe.yearly.map((y) => String(y.year)), y: pipe.yearly.map((y) => y.n_events),
                    marker: { color: pipe.yearly.map((y) => (y.full_year ? "#3987e5" : "rgba(57,135,229,0.35)")) },
                    customdata: pipe.yearly.map((y) => [y.n_detections, y.months_in_record, y.calibration.version ?? "none"]),
                    hovertemplate: "%{x}: %{y} fire events<br>%{customdata[0]} detections · %{customdata[1]} months in record<br>calibration %{customdata[2]}<extra></extra>" }]} />
              </div>}
              <p>{pipe.change.status === "computed"
                ? <>Trend: <b>{pipe.change.direction}</b> ({(pipe.change.slope_events_per_year ?? 0) >= 0 ? "+" : ""}{pipe.change.slope_events_per_year} events per year; 90% range {pipe.change.slope_90?.[0]} to {pipe.change.slope_90?.[1]}).</>
                : pipe.change.note ?? "Not enough complete years for a trend."}</p>
              <p className="hz-src">Faded bars are partial years. {pipe.change.caveat ?? ""}</p>
            </>
          ) : history ? (
            <>
              {annual.every((a) => !a.activity) ? <p className="hz-src">No fire activity was recorded in any year of the record.</p> : <div style={{ height: 220 }}>
                <Plot config={CONFIG} style={{ width: "100%", height: "100%" }} layout={{ ...LAYOUT, yaxis: { ...LAYOUT.yaxis, title: { text: "yearly activity" } } }}
                  data={[{ type: "bar", x: annual.map((a) => String(a.year)), y: annual.map((a) => a.activity),
                    marker: { color: annual.map((a) => (a.months === 12 ? "#3987e5" : "rgba(57,135,229,0.35)")) },
                    customdata: annual.map((a) => [a.hotspots, a.months]),
                    hovertemplate: "%{x}: %{y:.1f} harmonized activity<br>%{customdata[0]} raw hotspots · %{customdata[1]} months in record<extra></extra>" }]} />
              </div>}
              {history.change_points.change_points.length
                ? <ul className="hz-list">{history.change_points.change_points.map((c) => <li key={c.date}>{c.description}</li>)}</ul>
                : <p>{history.change_points.note ?? "No statistically detected change in the long-term pattern."}</p>}
              <p className="hz-src">Faded bars are partial years. {history.change_points.caveat ?? ""}</p>
            </>
          ) : <p>{historyWait}</p>}
        </Q>

        <Q n={6} q="Is the current activity unusual?" status={pipe ? pipe.unusual.category ?? pipe.unusual.status : cmp?.overall_category ?? cmp?.status ?? (history || fullError ? "awaiting data" : "loading")}
          source={pipe ? "FlameSeek pipeline: fire events in the last 30 days, robust z-score against the same dates in earlier years" : "Fire Memory: robust z-score against the same dates in earlier years"}>
          {pipe ? (pipe.unusual.status === "computed" ? (
            <p>From {pipe.unusual.window?.start} to {pipe.unusual.window?.end}: <b>{pipe.unusual.current_events}</b> fire event(s), against {pipe.unusual.history_events?.join(", ")} on the same dates in the {pipe.unusual.history_events?.length} earlier years. That is <b>{pipe.unusual.category}</b>
              {pipe.unusual.robust_z != null ? <> (robust z = {pipe.unusual.robust_z}; higher than {pipe.unusual.percentile_rank}% of earlier years)</> : null}.</p>
          ) : <p>{pipe.unusual.note ?? "Not enough history for a comparison."}</p>
          ) : cmp && cmp.overall_category && (cmp.current?.harmonized_activity ?? 0) === 0 && (cmp.percentile_rank ?? 0) === 0 ? (
            <p>No fire activity from {cmp.window?.start} to {cmp.window?.end}, and none on the same dates in the {cmp.history_years?.length} earlier years: <b>{cmp.overall_category}</b> for this place.</p>
          ) : cmp && cmp.overall_category ? (
            <p>From {cmp.window?.start} to {cmp.window?.end}, activity was <b>{cmp.overall_category}</b>: more than {cmp.percentile_rank}% of the {cmp.history_years?.length} earlier years over the same dates (robust z = {cmp.robust_z}).
              {cmp.flags.length ? <> {cmp.flags.map((f) => f.label).join("; ")}.</> : null}</p>
          ) : <p>{cmp?.note ?? (history ? "Not enough history for a comparison." : historyWait)}</p>}
        </Q>

        <Q n={7} q="How reliable are the observations?" status={quality ? "computed" : loadingMemory ? "loading" : "awaiting data"} source={quality?.method}>
          {quality ? (
            <>
              <p>The ground was unobservable (cloud or no satellite pass) on <b>{quality.pct_days_unobservable}%</b> of days; average viewing score <b>{quality.mean_sufficiency_score}</b> out of 100.
                {" "}{memory?.calibration?.note ? `MODIS and VIIRS are put on one scale: ${memory.calibration.note}` : ""}</p>
              <div className="hz-legend" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
                {Object.entries(quality.counts).map(([k, v]) => <span key={k}>{quality.labels[k] ?? k}: <b>{v}</b> days</span>)}
              </div>
              {pipe && (
                <>
                  <p>Pipeline checks: <b>{pipe.quality.clean_detections}</b> clean detections used, <b>{pipe.quality.low_confidence_set_aside}</b> low-confidence set aside; fire energy conserved on the grid: <b>{pipe.quality.energy_conservation.pass ? "pass" : "fail"}</b>. Latent fire rate (λ): {pipe.quality.lambda}.</p>
                  <ul className="hz-list">
                    {pipe.yearly.map((y) => <li key={y.year}><b>{y.year}</b>: {y.calibration.status}{y.calibration.offset_min != null ? ` (Aqua crossed ${Math.round(Math.abs(y.calibration.offset_min))} min ${y.calibration.offset_min >= 0 ? "after" : "before"} 13:30)` : ""}</li>)}
                  </ul>
                </>
              )}
              <p className="hz-src">Satellite hotspots are observations, not confirmed fires. No fire seen ≠ no fire.{pipe ? " Calibration v2 was validated on 2016 data, when Aqua and Suomi-NPP still passed together; years after Aqua's orbit drifted use the provisional v1." : ""}</p>
            </>
          ) : <p>{loadingMemory ? "Building the record…" : "awaiting data"}</p>}
        </Q>

        <div id="risk" />
        <Q n={8} q="What does a validated model estimate about future fire occurrence?" status={risk?.status === "computed" ? `${risk.label}` : risk ? "withheld" : history || fullError ? "awaiting data" : "loading"} source={risk?.method}>
          {risk?.status === "computed" && risk.probability != null && risk.validation ? (
            <>
              <p>Chance of {risk.event}: <b>{Math.round(risk.probability * 100)}%</b>. In {risk.years_with_fire_in_window} of {risk.years_checked} past years, fire occurred in this same window.</p>
              <p>Validation ({risk.validation.method}, n = {risk.validation.n}): Brier Skill Score <b>{risk.validation.brier_skill_score ?? "—"}</b> against {risk.validation.reference} — {risk.skill}.</p>
              <p className="hz-src">A climatological baseline from this place's own history, not a weather-driven forecast. It does not know about this season's weather or fuel.</p>
            </>
          ) : <p>{risk ? <>Withheld: {risk.reason ?? "insufficient history"}.{years < 10 && <> <button className="hz-link-btn" onClick={() => setYears(10)}>Use 10 years of history</button> to compute it.</>}</> : histReady ? "Re-run the analysis to compute the area estimate." : historyWait}</p>}
        </Q>
      </section>

      <section className="methods" style={{ marginTop: 36 }}>
        <h3>Explore in depth</h3>
        <div className="method-grid">
          {[
            ["/fire-memory", "Fire Memory", "Day-by-day history, calendar and data sources."],
            ["/fire-dna", "Fire DNA", "Seasonal signature, trends and unusual activity."],
            ["/fire-calendar", "Burning Calendar", "Month-by-month burning pattern."],
            ["/fire-events", "Fire Events", "Recent fire events as true burned-ground outlines."],
            ["/fire-map", "FireNow", "Live 3D globe of current fires."],
          ].map(([to, h, p], i) => (
            <Link key={to} to={featureHref(to, aoi, Boolean(lockedArea))} className="method-card glass-card" style={{ textDecoration: "none" }}>
              <span className="method-index" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
              <h4>{h}</h4><p>{p}</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
