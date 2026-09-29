import { useEffect, useState } from "react";
import { getDataSources } from "../api/client";
import VerificationPanel from "../components/VerificationPanel";
import type { DataSource } from "../types/api";

const METHODS = [
  ["Harmonization", "Detections are spread over the ~1 km (0.01°) MODIS-scale grid in proportion to their FIRMS pixel footprint (scan × track). VIIRS activity is rescaled to MODIS-equivalent units using the median MODIS/VIIRS ratio on co-observed day-blocks."],
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
    <main className="content-page">
      <p className="eyebrow">Transparency</p>
      <h2>Sources & Methods</h2>
      <p className="lead">
        Every result names its source and processing method. <strong>Automated</strong> sources are queried by the backend. <strong>Review links</strong> are offered for an analyst to check
        and are never counted as checked evidence.
      </p>
      {groups.map((group) => (
        <section key={group} className="source-group">
          <h3>{group}</h3>
          <div className="source-grid">
            {sources.filter((s) => s.group === group).map((source) => (
              <article key={source.name} className="source-card">
                <h3>{source.name}</h3>
                <p>{source.description}</p>
                <span className={`access-pill ${source.access.replace(/\s/g, "-")}`}>{source.access}</span>
                {source.url && <a href={source.url} target="_blank" rel="noreferrer">Visit source</a>}
              </article>
            ))}
          </div>
        </section>
      ))}
      <section className="methods">
        <h3>Methods</h3>
        <dl className="kv methods-list">
          {METHODS.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </section>
      <VerificationPanel />
    </main>
  );
}
