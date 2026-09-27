import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCurrentHotspots } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";

type LiveSummary = {
  label: string;
  detail: string;
};

export default function HomePage() {
  const [liveSummary, setLiveSummary] = useState<LiveSummary>({
    label: "LIVE FIRMS SYNC",
    detail: "Checking MODIS and VIIRS observations...",
  });

  useEffect(() => {
    let cancelled = false;

    getCurrentHotspots(DEFAULT_SENSORS, 1, 1)
      .then((response) => {
        if (cancelled) return;
        const detected = Number(response.metadata.filtered_hotspot_count ?? 0);
        setLiveSummary({
          label: "LIVE FIRMS SYNC",
          detail: detected > 0
            ? `${detected.toLocaleString()} filtered observations in the current one-day window.`
            : "No filtered observations returned in the current one-day window.",
        });
      })
      .catch(() => {
        if (!cancelled) {
          setLiveSummary({
            label: "LIVE FIRMS SYNC",
            detail: "FIRMS is unavailable right now. Open the Fire Globe to retry.",
          });
        }
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
          <p className="mission-kicker">Global Active-Fire Intelligence</p>
          <h2 id="mission-title">FIREHARMONY</h2>
          <p className="mission-statement">
            Satellite observations, seasonal burning patterns, and evidence-led fire validation on one living planet.
          </p>
          <div className="mission-actions">
            <Link className="mission-action primary" to="/fire-map">Open Live Globe</Link>
            <Link className="mission-action" to="/critical-periods">Explore Fire Calendar</Link>
          </div>
        </div>
        <aside className="mission-readout" aria-label="FireHarmony system status">
          <div>
            <span className="mission-status-dot" />
            <p>{liveSummary.label}</p>
          </div>
          <strong>MODIS + VIIRS</strong>
          <small>{liveSummary.detail}</small>
          <dl>
            <div><dt>Detection</dt><dd>NASA FIRMS</dd></div>
            <div><dt>Validation</dt><dd>Evidence-led</dd></div>
            <div><dt>View</dt><dd>3D Earth</dd></div>
          </dl>
        </aside>
        <div className="mission-footnote">
          <span>01</span>
          <p>Original satellite detection remains separate from fire validation status.</p>
        </div>
      </section>
      <section className="mission-paths" aria-label="FireHarmony tools">
        <Link to="/fire-map"><span>01</span><strong>Live Fire Globe</strong><small>Inspect current, geolocated FIRMS detections.</small></Link>
        <Link to="/critical-periods"><span>02</span><strong>Burning Calendar</strong><small>Compare activity against seasonal history.</small></Link>
        <Link to="/data-sources"><span>03</span><strong>Evidence Sources</strong><small>Review satellite, government, and news inputs.</small></Link>
      </section>
    </main>
  );
}
