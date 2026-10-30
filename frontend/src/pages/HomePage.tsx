import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "react-plotly.js";
import { getCurrentHotspots, getEvents } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";
import type { FireEventSummary, HotspotRecord } from "../types/api";

type SensorCounts = Record<"modis" | "viirs_snpp" | "viirs_noaa20" | "viirs_noaa21", number>;

const EMPTY_COUNTS: SensorCounts = { modis: 0, viirs_snpp: 0, viirs_noaa20: 0, viirs_noaa21: 0 };
const SENSOR_LABELS = ["MODIS", "S-NPP", "NOAA-20", "NOAA-21"];

const STORY = [
  { n: "01", title: "Fire Memory", q: "What normally happened in this area in the past?", route: "/fire-memory", icon: "▤", how: "Four-Witness consistent record, seasonal profiles, robust anomalies and change points." },
  { n: "02", title: "Fire Now", q: "What are satellites observing right now?", route: "/fire-map", icon: "◉", how: "Live FIRMS detections on a 3D globe with footprint uncertainty and observation quality." },
  { n: "03", title: "Fire Identity", q: "Which observations belong to the same evolving fire?", route: "/fire-map", icon: "⌕", how: "Spatio-temporal event reconstruction and inferred behaviour states." },
  { n: "04", title: "Fire Evidence", q: "Do other satellites, agencies or local reports support it?", route: "/fire-map", icon: "▣", how: "Later passes, geostationary satellites, agencies and news form one evidence case." },
  { n: "05", title: "Fire Past", q: "How did similar historical fires behave?", route: "/fire-map", icon: "▥", how: "Same-age analogue search over past seasons in the selected region." },
  { n: "06", title: "Fire Future", q: "Where might new satellite-observed activity appear next?", route: "/fire-map", icon: "◷", how: "A validated 6/12/24 h activity corridor, or FORECAST WITHHELD." },
  { n: "07", title: "Exposure", q: "What lies inside the possible activity corridor?", route: "/fire-map", icon: "♟", how: "Population, roads, settlements, land cover and critical facilities." },
] as const;

const WORKFLOW = [
  "MODIS + VIIRS", "AOI & region selection", "Sensor detection profile", "Time-of-day correction",
  "Consistent record and satellite layer", "Observation effort", "Fused fire probability", "Burning activity calendar",
  "Current vs historical", "Anomaly detection", "3D globe", "Fire event reconstruction", "Behaviour analysis",
  "Reverse geocoding", "Regional satellite verification", "Government sources", "Country-specific news",
  "NLP event extraction", "Geographic matching", "Temporal matching", "Fire Case evidence block",
  "Three-part answer", "Historical analogues", "Short-term forecast", "Forecast corridor", "Exposure analysis",
];

function formatAge(date: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 60000));
  if (minutes < 60) return `${Math.max(1, minutes)} min ago`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.floor(hours / 24)} d ago`;
}

function sensorFamily(sensor: string) {
  return sensor === "modis" ? "MODIS" : "VIIRS";
}

function SatelliteIcon() {
  return <img src="/satellite-realistic-v2.png" alt="" aria-hidden="true" decoding="async" />;
}

export default function HomePage() {
  const [hotspots, setHotspots] = useState<HotspotRecord[]>([]);
  const [events, setEvents] = useState<FireEventSummary[]>([]);
  const [counts, setCounts] = useState<SensorCounts>(EMPTY_COUNTS);
  const [totalDetections, setTotalDetections] = useState<number | null>(null);
  const [sourceMode, setSourceMode] = useState<"live" | "cached" | "demo" | "unavailable">("live");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadHotspots = async () => {
      try {
        return { response: await getCurrentHotspots(DEFAULT_SENSORS, 1, 600, undefined, false), usedDemo: false };
      } catch {
        return { response: await getCurrentHotspots(DEFAULT_SENSORS, 1, 600, undefined, true), usedDemo: true };
      }
    };
    const loadEvents = async () => {
      try {
        return await getEvents(2, 40, false);
      } catch {
        return await getEvents(2, 40, true);
      }
    };

    Promise.allSettled([loadHotspots(), loadEvents()])
      .then(([hotspotResult, eventResult]) => {
        if (cancelled) return;

        if (hotspotResult.status === "fulfilled") {
          const { response, usedDemo } = hotspotResult.value;
          const bySensor = (response.metadata.filtered_by_sensor ?? response.metadata.returned_by_sensor ?? {}) as Record<string, number>;
          setHotspots(response.hotspots);
          setCounts({
            modis: Number(bySensor.modis ?? 0),
            viirs_snpp: Number(bySensor.viirs_snpp ?? 0),
            viirs_noaa20: Number(bySensor.viirs_noaa20 ?? 0),
            viirs_noaa21: Number(bySensor.viirs_noaa21 ?? 0),
          });
          setTotalDetections(Number(response.metadata.filtered_hotspot_count ?? response.hotspots.length));
          const dataSource = String(response.metadata.data_source ?? "live");
          setSourceMode(usedDemo || dataSource === "demo" ? "demo" : dataSource.includes("cached") ? "cached" : "live");
          setUpdatedAt(new Date());
        } else {
          setSourceMode("unavailable");
          setError("NASA FIRMS is temporarily unavailable. The interface remains ready to retry in Fire Now.");
        }

        if (eventResult.status === "fulfilled") setEvents(eventResult.value.events);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const latestEvents = useMemo(
    () => [...events].sort((a, b) => +new Date(b.latest_detection) - +new Date(a.latest_detection)).slice(0, 3),
    [events],
  );
  const multiEvents = events.filter((event) => event.observation_count > 1).length;
  const totalFrp = hotspots.reduce((sum, hotspot) => sum + (hotspot.frp ?? 0), 0);
  const activePlatforms = new Set(hotspots.map((hotspot) => hotspot.satellite || hotspot.sensor)).size;
  const strongest = [...hotspots].sort((a, b) => (b.frp ?? 0) - (a.frp ?? 0))[0];

  return (
    <main className="fs-home">
      <section className="fs-hero fs-cinematic" aria-labelledby="fs-title">
        <div className="fs-grid-overlay" aria-hidden="true" />
        <Link to="/fire-memory" className="fs-edge-world fs-memory-world" aria-label="Open Fire Memory"><span>Fire Memory</span><b>‹</b></Link>
        <Link to="/fire-map" className="fs-edge-world fs-now-world" aria-label="Open Fire Now"><b>›</b><span>Fire Now</span></Link>

        <div className="fs-cinematic-title">
          <h2 id="fs-title">FlameSeek</h2>
          <p className="fs-path">Past → Present → Identify → Verify → Compare → Forecast → Exposure.</p>
          <p className="fs-caveat">A satellite hotspot is an observation, not automatically a confirmed wildfire.</p>
          <div className="fs-actions">
            <Link to="/fire-map" className="fs-button primary">Explore <span>→</span></Link>
            <Link to="/fire-memory" className="fs-button">Build Fire Memory</Link>
          </div>
        </div>

        <div className="fs-globe-layer fs-static-earth">
          <img src="/flameseek-earth-hero.png" alt="Cinematic Earth centered on Asia, used as decorative artwork" decoding="async" fetchPriority="high" />
        </div>
        <div className="fs-orbits" aria-hidden="true"><i /><i /><i /></div>
        <p className="fs-schematic-note">Schematic witness paths · not real-time orbital positions</p>
        <div className="sat-label sat-terra"><span><SatelliteIcon /></span><b>TERRA</b><small>MODIS</small></div>
        <div className="sat-label sat-aqua"><span><SatelliteIcon /></span><b>AQUA</b><small>MODIS</small></div>
        <div className="sat-label sat-snpp"><span><SatelliteIcon /></span><b>SUOMI NPP</b><small>VIIRS</small></div>
        <div className="sat-label sat-n20"><span><SatelliteIcon /></span><b>NOAA-20</b><small>VIIRS</small></div>
        <div className="sat-label sat-n21"><span><SatelliteIcon /></span><b>NOAA-21</b><small>VIIRS</small></div>

        <div className={`fs-connection ${sourceMode}`}>
          <i />{loading ? "Connecting to NASA FIRMS…" : sourceMode === "live" ? "LIVE NASA DATA · MODIS + VIIRS" : sourceMode === "cached" ? "CACHED NASA DATA · MODIS + VIIRS" : sourceMode === "demo" ? "DEMONSTRATION DATA" : "LIVE FEED UNAVAILABLE"}<span>›</span>
        </div>
        <aside className="fs-right-rail">
          <article className="fs-panel fs-code-card">
            <header><span>CODE</span><b className={sourceMode}>{sourceMode === "live" ? "● LIVE" : sourceMode === "cached" ? "● CACHED" : sourceMode === "demo" ? "● DEMO" : "○ OFFLINE"}</b></header>
            <h3>BURN.NRT</h3>
            <dl>
              <div><dt>Dataset</dt><dd>NASA<br />FIRMS</dd></div><div><dt>Observations</dt><dd>MODIS<br />+ VIIRS</dd></div>
              <div><dt>Update</dt><dd>3 h<br />NRT</dd></div><div><dt>Grid</dt><dd>~1 km<br />0.01°</dd></div>
            </dl>
            <footer><span>Purpose</span><strong>Wildfire situational awareness</strong></footer>
          </article>
          <article className="fs-panel fs-live-card">
            <header><span className="pulse-dot" /> Live insights</header>
            {strongest ? <Link to="/fire-map" className="fs-coordinate"><span className="target-icon">◎</span><p><small>STRONGEST RETURN</small><strong>{strongest.lat.toFixed(2)}°, {strongest.lon.toFixed(2)}°</strong><em>{sensorFamily(strongest.sensor)} · {strongest.frp?.toFixed(1) ?? "—"} MW FRP</em></p><b>›</b></Link> : <div className="fs-card-skeleton">Waiting for an observation…</div>}
          </article>
        </aside>

        <div className="fs-telemetry" aria-label="FlameSeek observation summary">
          <div><span>◉</span><p><small>Dataset</small><strong>NASA FIRMS</strong></p></div>
          <div><span>♨</span><p><small>Observations</small><strong>MODIS + VIIRS</strong></p></div>
          <div><span>◫</span><p><small>Platforms</small><strong>Five witnesses</strong></p></div>
          <div><span>⌁</span><p><small>Current returns</small><strong>{totalDetections === null ? "—" : totalDetections.toLocaleString()}</strong></p></div>
          <div><span>⌖</span><p><small>Reconstructed</small><strong>{events.length} events</strong></p></div>
          <div><span>◷</span><p><small>Checked</small><strong>{updatedAt ? updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Pending"}</strong></p></div>
        </div>
      </section>

      {error && <div className="fs-data-alert" role="status">{error}</div>}

      <section className="fs-snapshot" aria-label="Current fire intelligence snapshot">
        <article className="fs-panel fs-chart-card">
          <header><h3>Detections by sensor</h3><small>RAW OBSERVATIONS · LAST 24 H</small></header>
          <Plot
            data={[{ type: "bar", x: SENSOR_LABELS, y: [counts.modis, counts.viirs_snpp, counts.viirs_noaa20, counts.viirs_noaa21], marker: { color: ["#45d9ff", "#42e8d4", "#388fff", "#9e5cff"], line: { color: "#86e8ff", width: 1 } }, hovertemplate: "%{x}<br>%{y:,} observations<extra></extra>" }]}
            layout={{ autosize: true, height: 120, margin: { l: 34, r: 8, t: 8, b: 28 }, paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#8da9c7", family: "Inter, sans-serif", size: 9 }, xaxis: { fixedrange: true, showgrid: false }, yaxis: { fixedrange: true, rangemode: "tozero", gridcolor: "rgba(77,190,255,.11)", zeroline: false }, showlegend: false }}
            config={{ displayModeBar: false, responsive: true }} useResizeHandler style={{ width: "100%", height: "120px" }}
          />
        </article>

        <article className="fs-panel fs-events-card">
          <header><h3>Latest reconstructed events</h3><Link to="/fire-map">View all →</Link></header>
          <ul>
            {latestEvents.map((event) => (
              <li key={event.event_id}>
                <span className="event-flare">✦</span>
                <p><strong>{event.place_hint || `${event.centroid.lat.toFixed(2)}°, ${event.centroid.lon.toFixed(2)}°`}</strong><small>{event.observation_count} observations · {event.sensors.map(sensorFamily).filter((value, index, all) => all.indexOf(value) === index).join(" + ")}</small></p>
                <em>{formatAge(event.latest_detection)}</em><b>›</b>
              </li>
            ))}
            {!latestEvents.length && <li className="fs-empty-row">No reconstructed event is available yet.</li>}
          </ul>
        </article>

        <article className="fs-panel fs-metrics-card">
          <header><h3>Fire events snapshot</h3><small>OBSERVATION ≠ INCIDENT</small></header>
          <ul>
            {[
              ["Raw hotspot observations", totalDetections, 92], ["Reconstructed events", events.length, 70],
              ["Multi-detection events", multiEvents, 56], ["Active sensor platforms", activePlatforms, 42],
              ["Observed fire power", totalFrp ? `${Math.round(totalFrp).toLocaleString()} MW` : "—", 34],
            ].map(([label, value, width]) => <li key={String(label)}><span>{label}</span><i><u style={{ width: `${width}%` }} /></i><b>{value ?? "—"}</b></li>)}
          </ul>
        </article>
      </section>

      <section className="fs-story">
        <p className="fs-section-kicker">The seven-stage fire story</p>
        <div className="fs-story-grid">
          {STORY.map((stage) => (
            <Link to={stage.route} key={stage.n} className="fs-panel fs-story-card"><span className="story-number">{stage.n}</span><span className="story-icon">{stage.icon}</span><p><strong>{stage.title}</strong><small>{stage.q}</small><em>{stage.how}</em></p><b>›</b></Link>
          ))}
        </div>
      </section>

      <section className="fs-meanings" aria-label="How to read FlameSeek">
        <article className="fs-panel"><span>◆</span><p><strong>Observation</strong><small>What MODIS and VIIRS actually detected: anomaly, time, footprint, FRP and confidence. Absence under clouds is reported as UNKNOWN, not “no fire”.</small></p><b>›</b></article>
        <article className="fs-panel"><span>◉</span><p><strong>Inference</strong><small>What the system considers: harmonized activity, anomaly categories, reconstructed events, behaviour states, evidence status and score.</small></p><b>›</b></article>
        <article className="fs-panel"><span>▤</span><p><strong>External evidence</strong><small>What independent satellites, government agencies and local news report, matched by distance and time with links to original sources.</small></p><b>›</b></article>
        <article className="fs-panel"><span>⌁</span><p><strong>Forecast</strong><small>Where new satellite-observed activity may appear in the next 6 to 24 hours as a probability corridor—not a physical fire-spread prediction.</small></p><b>›</b></article>
      </section>

      <section className="fs-workflow"><p className="fs-section-kicker">Full explore</p><div>{WORKFLOW.map((step) => <span key={step}>◈ {step}</span>)}</div></section>
    </main>
  );
}
