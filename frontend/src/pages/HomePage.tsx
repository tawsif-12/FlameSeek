import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCurrentHotspots } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";

type LiveSummary = { label: string; detail: string };

const STORY = [
  { n: "01", title: "Fire Memory", q: "What normally happened in this area in the past?", where: "/fire-memory", how: "26-year harmonized MODIS/VIIRS calendar, seasonal profiles, robust anomalies, change points" },
  { n: "02", title: "Fire Now", q: "What are satellites observing right now?", where: "/fire-map", how: "Live FIRMS detections on a 3D globe, with footprint uncertainty and observation quality" },
  { n: "03", title: "Fire Identity", q: "Which observations belong to the same evolving fire?", where: "/fire-map", how: "Spatio-temporal event reconstruction and inferred behaviour states" },
  { n: "04", title: "Fire Evidence", q: "Do other satellites, agencies or local reports support it?", where: "/fire-map", how: "GOES, Landsat, Sentinel-2, EFFIS, CWFIS, GDACS, NIFC, NSW RFS and news NLP, fused into an explainable status" },
  { n: "05", title: "Fire Past", q: "How did similar historical fires behave?", where: "/fire-map", how: "Same-age analogue search (KNN, Mahalanobis) over past seasons in the region" },
  { n: "06", title: "Fire Future", q: "Where might new satellite-observed activity appear next?", where: "/fire-map", how: "6/12/24 h corridor from validated baselines or LightGBM, or FORECAST WITHHELD" },
  { n: "07", title: "Exposure", q: "What lies inside the possible activity corridor?", where: "/fire-map", how: "WorldPop population plus OpenStreetMap roads, villages, farmland, forests, schools, hospitals and power" },
];

const WORKFLOW = [
  "MODIS + VIIRS", "Historical and current collection", "Spatial harmonization", "Sensor calibration", "Harmonized Observed Burning Activity",
  "Observation sufficiency and uncertainty", "Burning activity calendar", "Current vs historical", "Anomaly detection", "3D globe",
  "Fire event reconstruction", "Behaviour analysis", "Reverse geocoding", "Regional satellite verification", "Government sources",
  "Country-specific news", "NLP event extraction", "Geographic matching", "Temporal matching", "Evidence fusion",
  "Explainable validation", "Historical analogues", "Short-term forecast", "Forecast corridor", "Exposure analysis",
];

export default function HomePage() {
  const [liveSummary, setLiveSummary] = useState<LiveSummary>({ label: "LIVE FIRMS SYNC", detail: "Checking MODIS and VIIRS observations..." });

  useEffect(() => {
    let cancelled = false;
    getCurrentHotspots(DEFAULT_SENSORS, 1, 1)
      .then((response) => {
        if (cancelled) return;
        const detected = Number(response.metadata.filtered_hotspot_count ?? 0);
        setLiveSummary({
          label: "LIVE FIRMS SYNC",
          detail: detected > 0 ? `${detected.toLocaleString()} filtered observations in the current one-day window.` : "No filtered observations returned in the current one-day window.",
        });
      })
      .catch(() => {
        if (!cancelled) setLiveSummary({ label: "LIVE FIRMS SYNC", detail: "FIRMS is unavailable right now. Open the Fire Globe to retry." });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mission-home">
      <section className="mission-hero" aria-labelledby="mission-title">
        <div className="mission-earth" aria-hidden="true">
          <img src="https://images-assets.nasa.gov/image/PIA18033/PIA18033~orig.jpg" alt="" />
        </div>
        <div className="mission-scanlines" aria-hidden="true" />
        <div className="mission-copy">
          <p className="mission-kicker">Global Fire Intelligence</p>
          <h2 id="mission-title">BURNING_ACTIVITY</h2>
          <p className="mission-statement">Past → Present → Identify → Verify → Compare → Forecast → Exposure. A satellite hotspot is an observation, not automatically a confirmed wildfire.</p>
          <div className="mission-actions">
            <Link className="mission-action primary" to="/fire-map">Open Fire Now</Link>
            <Link className="mission-action" to="/fire-memory">Build Fire Memory</Link>
          </div>
        </div>
        <aside className="mission-readout" aria-label="Burning_Activity system status">
          <div>
            <span className="mission-status-dot" />
            <p>{liveSummary.label}</p>
          </div>
          <strong>MODIS + VIIRS</strong>
          <small>{liveSummary.detail}</small>
          <dl>
            <div><dt>Detection</dt><dd>NASA FIRMS</dd></div>
            <div><dt>Validation</dt><dd>Evidence-led</dd></div>
            <div><dt>Forecast</dt><dd>Validated or withheld</dd></div>
          </dl>
        </aside>
        <div className="mission-footnote">
          <span>01</span>
          <p>Observation, inference, external evidence and forecast are always kept separate.</p>
        </div>
      </section>

      <section className="story-section" aria-label="The seven-stage fire story">
        <p className="mission-kicker">The seven-stage fire story</p>
        <div className="story-grid">
          {STORY.map((s) => (
            <Link key={s.n} to={s.where} className="story-card">
              <span>{s.n}</span>
              <strong>{s.title}</strong>
              <em>{s.q}</em>
              <small>{s.how}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="separation-section" aria-label="What each result means">
        <article className="sep obs"><h3>Observation</h3><p>What MODIS and VIIRS actually detected: sensor, time, footprint, FRP, confidence. Absence under clouds is reported as UNKNOWN, not "no fire".</p></article>
        <article className="sep inf"><h3>Inference</h3><p>What the system concludes: harmonized activity, anomaly categories, fire events, inferred behaviour states, and the evidence status and score.</p></article>
        <article className="sep ext"><h3>External evidence</h3><p>What independent satellites, government agencies and local news report, matched by distance and time, always with a link to the original source.</p></article>
        <article className="sep fc"><h3>Forecast</h3><p>Where new satellite-observed activity may appear in the next 6 to 24 hours, as a probability corridor. It is issued only when validated against baselines.</p></article>
      </section>

      <section className="workflow-section" aria-label="Full system workflow">
        <p className="mission-kicker">Full workflow</p>
        <ol className="workflow-chain">
          {WORKFLOW.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </section>
    </main>
  );
}
