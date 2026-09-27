import { useEffect, useState } from "react";
import { DEFAULT_SENSORS } from "../context/AppContext";
import { getVerifiedHotspots, normalizeApiError } from "../api/client";
import type { VerifiedHotspotRecord } from "../types/api";

const VERDICT_LABELS: Record<VerifiedHotspotRecord["verification"]["verdict"], string> = {
  confirmed_fire: "Confirmed fire",
  needs_review: "Needs review",
  likely_false_positive: "Likely false positive",
};

export default function VerificationPanel() {
  const [hotspots, setHotspots] = useState<VerifiedHotspotRecord[]>([]);
  const [metadata, setMetadata] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await getVerifiedHotspots(DEFAULT_SENSORS);
      setHotspots(response.hotspots);
      setMetadata(response.metadata);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const verdictSummary = metadata.verdict_counts ? JSON.stringify(metadata.verdict_counts) : null;

  return (
    <section className="verification-panel">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Validation pipeline</p>
          <h2>Verified MODIS/VIIRS detections</h2>
        </div>
        <button className="secondary-button" type="button" onClick={load} disabled={loading}>
          {loading ? "Checking..." : "Refresh"}
        </button>
      </div>
      <p className="lead">
        FIRMS detections are scored with confidence, FRP, day/night reliability, and sensor resolution. Ambiguous points link straight to NASA Worldview imagery and national GDELT news search.
      </p>
      {verdictSummary && <p className="meta-text">Verdicts: {verdictSummary}</p>}
      {error && <p className="error-text">{error}</p>}
      <div className="verification-list">
        {hotspots.slice(0, 6).map((hotspot) => (
          <article key={`${hotspot.sensor}-${hotspot.lat}-${hotspot.lon}-${hotspot.acq_datetime}`} className={`verification-card ${hotspot.verification.verdict}`}>
            <div>
              <strong>{VERDICT_LABELS[hotspot.verification.verdict]}</strong>
              <span>{hotspot.sensor.toUpperCase()} - score {hotspot.verification.score}</span>
            </div>
            <dl>
              <div><dt>Country</dt><dd>{hotspot.verification.country_name}</dd></div>
              <div><dt>Place</dt><dd>{hotspot.verification.place_name}</dd></div>
              <div><dt>Location</dt><dd>{hotspot.lat.toFixed(3)}, {hotspot.lon.toFixed(3)}</dd></div>
              <div><dt>FRP</dt><dd>{hotspot.frp === null ? "N/A" : `${hotspot.frp.toFixed(1)} MW`}</dd></div>
              <div><dt>Confidence</dt><dd>{hotspot.confidence_pct.toFixed(0)}%</dd></div>
              <div><dt>Time</dt><dd>{new Date(hotspot.acq_datetime).toLocaleString()}</dd></div>
            </dl>
            <p>{hotspot.verification.evidence[0]?.signal ?? hotspot.verification.next_step}</p>
            <div className="verification-actions">
              <a href={hotspot.verification.imagery_url} target="_blank" rel="noreferrer">Worldview</a>
              <a href={hotspot.verification.national_news_url} target="_blank" rel="noreferrer">National news</a>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
