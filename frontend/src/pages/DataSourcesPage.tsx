import { useEffect, useState } from "react";
import { getDataSources } from "../api/client";
import VerificationPanel from "../components/VerificationPanel";
import type { DataSource } from "../types/api";

const METHODS = [
  ["Four-Witness harmonization", "Terra, Aqua, Suomi NPP and NOAA-20 are witnesses with known blind spots. MODIS same-overpass duplicates are merged. A detection profile, P(MODIS detects | VIIRS FRP, pixel area), is learned from Aqua/S-NPP matchups within 20 minutes; the Li et al. (2020) prior is used when matchups are too few. Every observation is converted to its Aqua 13:30 local-time equivalent with a fitted daily fire curve, which also removes orbit drift."],
  ["Two tiers and effort", "The consistent record keeps MODIS-level sensitivity from 2000 to today (VIIRS fires weighted by the chance MODIS would have seen them) and drives the calendar, trends and anomalies. The detailed layer keeps every VIIRS detection for the globe. Activity is expressed per clear-sky look (swath / track spacing × clear fraction)."],
  ["Fused fire probability", "Per 0.1° cell and local day: start from the cell's historical burning rate for that month; each detection raises the odds by detection chance / false-alarm rate, each clear miss lowers them; cloudy looks are ignored. Validated by the continuity test (no 2012 step) and the hide-one-witness test."],
  ["Fire Cases", "Every event opens a case. Stream A classifies later polar passes predicted from current orbits; stream B uses geostationary start, duration and end; stream C uses NLP-matched news and official reports. Background facts are land use, heat sources, the local burning season and repeat heat. Items vote for categories by reliability, and a type is named only above 50% with a 20-point lead."],
  ["Observation quality", "Each day is classed as reliable multi-sensor, valid no-fire, limited evidence, sensor disagreement (AMBIGUOUS), cloud-covered (UNKNOWN) or missing (INSUFFICIENT OBSERVATION). Cloud cover is an ERA5 proxy."],
  ["Anomalies", "Robust z = (x − median) / (1.4826·MAD) against the same ±7-day window in other years: Normal < 2, Above Normal 2–3.5, Unusual 3.5–5, Highly Unusual ≥ 5. These are statistical, not severity, labels."],
  ["Change points", "PELT on the deseasonalized log monthly series. Results are statistically detected changes, not proven physical shifts."],
  ["Fire events", "Detections link when ≤ 48 h apart and within both pixels' location uncertainty + 0.5 km + 2 km/day spread allowance (max 6 km). Behaviour states are inferred from FRP, count, extent, persistence and movement per 12 h overpass window."],
  ["Evidence fusion", "Expert-weighted components (satellite 20, repeat/agreement 10, regional satellite 20, official 25, news 10, geographic 8, temporal 7). The score is evidence strength, not a probability. 'Confirmed Fire' requires an official report within 15 km."],
  ["Analogues", "Historical events from the same ~60 km region and season are truncated to the current event's age, compared on standardized features with shrinkage-regularized Mahalanobis distance, and the 5 nearest are shown with their full outcomes."],
  ["Forecast", "Persistence, seasonal and wind-only baselines against LightGBM, tested on a temporal holdout (latest season) and a spatial holdout (east/west). LightGBM is used only if it wins on Brier score in both without losing footprint CSI; otherwise the best baseline is used, or FORECAST WITHHELD."],
  ["Exposure", "Corridor cells (p ≥ 0.1, any horizon) are overlaid with WorldPop population and OpenStreetMap assets. Assets are described as lying within or near the corridor, never as certain to be affected."],
];

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);

  useEffect(() => {
    getDataSources().then(setSources).catch(() => setSources([]));
  }, []);

  const groups = [...new Set(sources.map((s) => s.group))];

  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Transparency</p>
          <h2>Sources & Methods</h2>
          <p className="lead">
            Every result names its source and processing method. <strong>Automated</strong> sources are queried by the backend. <strong>Review links</strong> are offered for an analyst to check
            and are never counted as checked evidence.
          </p>
          <ul className="hero-chips">
            <li><span className="dot" />NASA FIRMS</li>
            <li><span className="dot" />Regional satellites</li>
            <li><span className="dot" />Government agencies</li>
            <li><span className="dot" />News NLP</li>
          </ul>
        </header>
      </div>
      {groups.map((group) => (
        <section key={group} className="source-group">
          <h3>{group}</h3>
          <div className="source-grid">
            {sources.filter((s) => s.group === group).map((source) => (
              <article key={source.name} className="source-card glass-card">
                <div className="source-card-glyph" aria-hidden="true">
                  <svg viewBox="0 0 32 32" width="26" height="26"><circle cx="16" cy="16" r="12" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" /><circle cx="16" cy="16" r="3" fill="currentColor" /><path d="M4 16h24M16 4v24" stroke="currentColor" strokeWidth="0.6" opacity="0.4" /></svg>
                </div>
                <h3>{source.name}</h3>
                <p>{source.description}</p>
                <div className="source-card-footer">
                  <span className={`access-pill ${source.access.replace(/\s/g, "-")}`}>{source.access}</span>
                  {source.url && <a href={source.url} target="_blank" rel="noreferrer">Visit ↗</a>}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
      <section className="methods">
        <h3>Methods</h3>
        <div className="method-grid">
          {METHODS.map(([k, v]) => (
            <article key={k} className="method-card glass-card">
              <span className="method-index" aria-hidden="true">{String(METHODS.findIndex(([kk]) => kk === k) + 1).padStart(2, "0")}</span>
              <h4>{k}</h4>
              <p>{v}</p>
            </article>
          ))}
        </div>
      </section>
      <VerificationPanel />
    </main>
  );
}
