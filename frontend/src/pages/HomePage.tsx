import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCurrentHotspots, getEvents } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";

type LiveStat = { detections: number | null; events: number | null; area: number | null };
type Insight = { kind: string; title: string; detail: string; badge: string; tone: "warn" | "info" | "ok" };

const STORY = [
  { n: "01", title: "Fire Memory", q: "What normally happened in this area in the past?", where: "/fire-memory", how: "Four-Witness consistent record (no 2012 VIIRS jump), seasonal profiles, robust anomalies, change points" },
  { n: "02", title: "Fire Now", q: "What are satellites observing right now?", where: "/fire-map", how: "Live FIRMS detections on a 3D globe, with footprint uncertainty and observation quality" },
  { n: "03", title: "Fire Identity", q: "Which observations belong to the same evolving fire?", where: "/fire-map", how: "Spatio-temporal event reconstruction and inferred behaviour states" },
  { n: "04", title: "Fire Evidence", q: "Do other satellites, agencies or local reports support it?", where: "/fire-map", how: "A Fire Case per detection: later passes, geostationary satellites, agencies and news NLP give one answer: real? what kind? still burning?" },
  { n: "05", title: "Fire Past", q: "How did similar historical fires behave?", where: "/fire-map", how: "Same-age analogue search (KNN, Mahalanobis) over past seasons in the region" },
  { n: "06", title: "Fire Future", q: "Where might new satellite-observed activity appear next?", where: "/fire-map", how: "6/12/24 h corridor from validated baselines or LightGBM, or FORECAST WITHHELD" },
  { n: "07", title: "Exposure", q: "What lies inside the possible activity corridor?", where: "/fire-map", how: "WorldPop population plus OpenStreetMap roads, villages, farmland, forests, schools, hospitals and power" },
];

const WORKFLOW = [
  "MODIS + VIIRS", "Clean, tag, de-duplicate", "Sensor detection profile", "Time-of-day correction", "Consistent record and detailed layer",
  "Observation effort", "Fused fire probability", "Burning activity calendar", "Current vs historical", "Anomaly detection", "3D globe",
  "Fire event reconstruction", "Behaviour analysis", "Reverse geocoding", "Regional satellite verification", "Government sources",
  "Country-specific news", "NLP event extraction", "Geographic matching", "Temporal matching", "Fire Case evidence block",
  "Three-part answer", "Historical analogues", "Short-term forecast", "Forecast corridor", "Exposure analysis",
];

export default function HomePage() {
  const [live, setLive] = useState<LiveStat>({ detections: null, events: null, area: null });
  const [status, setStatus] = useState<string>("Connecting to NASA FIRMS…");
  const [insights, setInsights] = useState<Insight[]>([]);

  useEffect(() => {
    let cancelled = false;
    getCurrentHotspots(DEFAULT_SENSORS, 1, 1)
      .then((r) => {
        if (cancelled) return;
        const d = Number(r.metadata.filtered_hotspot_count ?? 0);
        setLive((l) => ({ ...l, detections: d }));
        setStatus(d > 0 ? "Live · MODIS + VIIRS synchronised" : "Live · No filtered observations in the last day");
      })
      .catch(() => !cancelled && setStatus("FIRMS unavailable · open Fire Now to retry"));

    getEvents(2, 40)
      .then((r) => {
        if (cancelled) return;
        const total = r.events.length;
        const area = r.events.reduce((sum, e) => sum + (e.extent_km2 ?? 0), 0);
        setLive((l) => ({ ...l, events: total, area }));
        const top = [...r.events].sort((a, b) => (b.observation_count ?? 0) - (a.observation_count ?? 0)).slice(0, 3);
        setInsights(
          top.map<Insight>((e, i) => ({
            kind: ["Highest activity", "Watch this", "Recently spread"][i] ?? "Event",
            title: `${e.centroid.lat.toFixed(2)}°, ${e.centroid.lon.toFixed(2)}°`,
            detail: `${e.observation_count} detections · ${Math.round((e.extent_km2 ?? 0)).toLocaleString()} km² footprint`,
            badge: `EV-${e.event_id.slice(-6).toUpperCase()}`,
            tone: (e.observation_count ?? 0) > 200 ? "warn" : i === 1 ? "info" : "ok",
          })),
        );
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mission-home space-shell">
      <section className="mission-hero nasa-hero" aria-labelledby="mission-title">
        <div className="mission-earth" aria-hidden="true">
          <img src="https://images-assets.nasa.gov/image/PIA18033/PIA18033~orig.jpg" alt="" />
        </div>
        <div className="mission-scanlines" aria-hidden="true" />
        <div className="hero-orbit-rings" aria-hidden="true">
          <span /><span /><span />
        </div>

        <div className="hero-inner">
          <div className="hero-main">
            <p className="mission-kicker"><span className="dot" /> Global Fire Intelligence</p>
            <h2 id="mission-title">BURNING_ACTIVITY</h2>
            <p className="mission-statement">
              Past → Present → Identify → Verify → Compare → Forecast → Exposure.<br />
              A satellite hotspot is an observation, not automatically a confirmed wildfire.
            </p>
            <div className="explore-row">
              <Link to="/fire-map" className="explore-orb" aria-label="Open Fire Now">
                <span>EXPLORE</span>
              </Link>
              <Link to="/fire-memory" className="ghost-orb" aria-label="Build Fire Memory">
                <span>BUILD FIRE MEMORY</span>
              </Link>
            </div>
            <div className="ask-strip" role="note">
              <span className="ask-spark" aria-hidden="true">✦</span>
              <span>Ask the globe: which fire is closest to me, which has the strongest evidence, where might it spread…</span>
              <span className="ask-actions" aria-hidden="true"><i>?</i><i>::</i></span>
            </div>
          </div>

          <div className="hero-panels">
            <article className="glass-card code-card">
              <header>
                <h3>Code<br /><strong>BURN.NRT</strong></h3>
                <button type="button" aria-label="dismiss" className="glass-close">×</button>
              </header>
              <dl>
                <div><dt>Detection<br />source</dt><dd>NASA<br />FIRMS</dd></div>
                <div><dt>Observation<br />cadence</dt><dd>MODIS<br />+ VIIRS</dd></div>
                <div><dt>Update<br />window</dt><dd>3 h<br />NRT</dd></div>
                <div><dt>Grid<br />resolution</dt><dd>~1 km<br />0.01°</dd></div>
              </dl>
              <div className="code-purpose">
                <span>Purpose</span>
                <strong>Wildfire situational awareness</strong>
                <button type="button" className="plus" aria-label="expand">+</button>
              </div>
            </article>

            <aside className="glass-card insights-card" aria-label="AI Insights">
              <header>
                <p className="mission-kicker">✧ Live Insights</p>
              </header>
              <div className="insights-list">
                {insights.length === 0 && (
                  <>
                    <div className="insight-row skeleton"><span /><span /><span /></div>
                    <div className="insight-row skeleton"><span /><span /><span /></div>
                    <div className="insight-row skeleton"><span /><span /><span /></div>
                  </>
                )}
                {insights.map((ins) => (
                  <Link key={ins.badge} className="insight-row" to="/fire-map">
                    <div className="insight-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="34" height="34"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4" /><path d="M12 6c-2 3-4 5-4 8a4 4 0 0 0 8 0c0-2-2-4-4-8z" fill="currentColor" /></svg>
                    </div>
                    <div>
                      <em>{ins.badge}</em>
                      <strong>{ins.title}</strong>
                      <small className={`tone-${ins.tone}`}>{ins.kind} · {ins.detail}</small>
                    </div>
                    <span className="insight-jump" aria-hidden="true">↗</span>
                  </Link>
                ))}
              </div>
              <footer><small>Data refreshed at page load. Open Fire Now for live streaming.</small></footer>
            </aside>
          </div>
        </div>

        <div className="hero-readout-strip">
          <span className="mission-status-dot" />
          <p>{status}</p>
        </div>
      </section>

      <section className="dashboard-strip" aria-label="Live snapshot">
        <article className="dashboard-card">
          <header><h3>Detections by day</h3><span className="cta">↗</span></header>
          <p className="giant-metric">{live.detections === null ? "…" : live.detections.toLocaleString()}</p>
          <small>Filtered MODIS + VIIRS observations (last 24 h)</small>
          <div className="bar-mini" aria-hidden="true">
            {[70, 100, 50, 42, 66].map((h, i) => (
              <div key={i} style={{ height: `${h}%` }}><i>MODIS</i><i>VIIRS</i></div>
            ))}
          </div>
          <ul className="axis-labels"><li>MODIS</li><li>VIIRS</li><li>SNPP</li><li>NOAA-20</li><li>NOAA-21</li></ul>
        </article>

        <article className="dashboard-card">
          <header><h3>Latest events</h3><span className="cta">↗</span></header>
          <ul className="release-list">
            {insights.length ? insights.map((ins) => (
              <li key={ins.badge}>
                <span className="pill">{ins.badge}</span>
                <strong>{ins.title}</strong>
                <small>{ins.detail}</small>
              </li>
            )) : (
              <>
                <li className="skeleton"><span className="pill">EV-…</span><strong>Locating…</strong><small>–</small></li>
                <li className="skeleton"><span className="pill">EV-…</span><strong>Locating…</strong><small>–</small></li>
                <li className="skeleton"><span className="pill">EV-…</span><strong>Locating…</strong><small>–</small></li>
              </>
            )}
          </ul>
        </article>

        <article className="dashboard-card">
          <header><h3>Fire events snapshot</h3><span className="cta">↗</span></header>
          <ul className="purpose-list">
            <li><span>Multi-detection events</span><i style={{ width: "82%" }} /><b>{live.events ?? "–"}</b></li>
            <li><span>Total footprint (km²)</span><i style={{ width: "60%" }} /><b>{live.area === null ? "–" : Math.round(live.area).toLocaleString()}</b></li>
            <li><span>Anomaly categories</span><i style={{ width: "38%" }} /><b>4</b></li>
            <li><span>Evidence sources</span><i style={{ width: "72%" }} /><b>12+</b></li>
            <li><span>Forecast horizons</span><i style={{ width: "30%" }} /><b>3</b></li>
          </ul>
        </article>
      </section>

      <section className="story-section" aria-label="The seven-stage fire story">
        <p className="mission-kicker">✧ The seven-stage fire story</p>
        <div className="story-grid nasa-story-grid">
          {STORY.map((s) => (
            <Link key={s.n} to={s.where} className="story-card glass-card">
              <span>{s.n}</span>
              <strong>{s.title}</strong>
              <em>{s.q}</em>
              <small>{s.how}</small>
              <div className="story-card-glow" aria-hidden="true" />
            </Link>
          ))}
        </div>
      </section>

      <section className="separation-section space-sep" aria-label="What each result means">
        <article className="sep obs glass-card"><span className="chip">Observed</span><h3>Observation</h3><p>What MODIS and VIIRS actually detected: sensor, time, footprint, FRP, confidence. Absence under clouds is reported as UNKNOWN, not "no fire".</p></article>
        <article className="sep inf glass-card"><span className="chip">Inferred</span><h3>Inference</h3><p>What the system concludes: harmonized activity, anomaly categories, fire events, inferred behaviour states, and the evidence status and score.</p></article>
        <article className="sep ext glass-card"><span className="chip">External</span><h3>External evidence</h3><p>What independent satellites, government agencies and local news report, matched by distance and time, always with a link to the original source.</p></article>
        <article className="sep fc glass-card"><span className="chip">Forecast</span><h3>Forecast</h3><p>Where new satellite-observed activity may appear in the next 6 to 24 hours, as a probability corridor. It is issued only when validated against baselines.</p></article>
      </section>

      <section className="workflow-section" aria-label="Full system workflow">
        <p className="mission-kicker">✧ Full workflow</p>
        <ol className="workflow-chain">
          {WORKFLOW.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </section>
    </main>
  );
}
