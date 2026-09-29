import { useMemo, useState } from "react";
import Plot from "react-plotly.js";
import { normalizeApiError, runJob, startFireMemory } from "../api/client";
import AOISelector from "../components/AOISelector";
import WorldviewButton from "../components/WorldviewButton";
import { DEFAULT_SENSORS, SENSOR_LABELS, aoiBBox, describeAoi, useAppContext } from "../context/AppContext";
import type { FireMemoryResult, Job, SensorName } from "../types/api";

const CATEGORY_COLORS: Record<string, string> = {
  Normal: "#94a3b8",
  "Above Normal": "#f59e0b",
  Unusual: "#ea580c",
  "Highly Unusual": "#b91c1c",
};
const SEASON_COLORS: Record<string, string> = { peak: "#b91c1c", active: "#ea580c", moderate: "#f59e0b", quiet: "#cbd5e1", "no data": "#e2e8f0" };
const OBS_COLORS: Record<string, string> = {
  reliable_multi_sensor: "#15803d",
  valid_no_fire: "#86efac",
  limited_evidence: "#facc15",
  sensor_disagreement: "#f97316",
  cloud_obscured: "#64748b",
  missing_observation: "#1e293b",
};
const plotLayout = { autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Inter, sans-serif", size: 12 } };

export default function FireMemoryPage() {
  const { aoi, sensors, setSensors, memory, setMemory } = useAppContext();
  const [years, setYears] = useState(5);
  const [windowDays, setWindowDays] = useState(30);
  const [job, setJob] = useState<Job<FireMemoryResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = job?.status === "queued" || job?.status === "running";

  async function run() {
    if (!aoi) return;
    setError(null);
    try {
      const result = await runJob(startFireMemory(aoi, years, sensors, windowDays), setJob);
      setMemory(result);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setJob(null);
    }
  }

  const toggleSensor = (sensor: SensorName) => setSensors(sensors.includes(sensor) ? sensors.filter((s) => s !== sensor) : [...sensors, sensor]);

  return (
    <main className="memory-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="memory-intro nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Stage 1 · Fire Memory</p>
          <h2>What normally happens in this area?</h2>
          <p className="lead">
            Up to 26 years of MODIS and VIIRS observations are harmonized onto a common ~1 km grid. The result is a burning activity calendar,
            seasonal profiles, and a comparison of current activity with the area's own history.
          </p>
          <ul className="hero-chips">
            <li><span className="dot" />26-year record</li>
            <li><span className="dot" />Harmonized MODIS + VIIRS</li>
            <li><span className="dot" />Robust anomalies</li>
            <li><span className="dot" />PELT change points</li>
          </ul>
        </header>
      </div>
      <section className="memory-setup glass-card">
        <div className="memory-setup-map">
          <h3>1. Area of interest</h3>
          <AOISelector />
        </div>
        <div className="memory-setup-controls">
          <h3>2. Record and sensors</h3>
          <label>
            History length
            <select value={years} onChange={(e) => setYears(Number(e.target.value))}>
              {[1, 2, 3, 5, 10, 15, 20, 26].map((y) => (
                <option key={y} value={y}>{y} year{y > 1 ? "s" : ""}{y >= 10 ? " (slow on first run)" : ""}</option>
              ))}
            </select>
          </label>
          <label>
            Current-vs-history window
            <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
              {[14, 30, 60, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
            </select>
          </label>
          <div className="sensor-grid">
            {DEFAULT_SENSORS.map((sensor) => (
              <label key={sensor} className="checkbox-label">
                <input type="checkbox" checked={sensors.includes(sensor)} onChange={() => toggleSensor(sensor)} />
                {SENSOR_LABELS[sensor]}
              </label>
            ))}
          </div>
          <button className="primary-button" type="button" disabled={!aoi || running || sensors.length === 0} onClick={run}>
            {running ? "Building Fire Memory..." : "Build Fire Memory"}
          </button>
          {job && (
            <div className="job-progress" role="status">
              <div><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <small>{job.message}</small>
            </div>
          )}
          {error && <p className="error-text">{error}</p>}
          <p className="meta-text">The archive is downloaded once per area and cached, so later runs are fast. FIRMS allows about 5000 requests per 10 minutes, which covers 26 years of four sensors.</p>
        </div>
      </section>
      {memory && <MemoryResults memory={memory} />}
    </main>
  );
}

function MemoryResults({ memory }: { memory: FireMemoryResult }) {
  const cmp = memory.current_vs_historical;
  const bbox = aoiBBox(memory.aoi as never) ?? (memory.aoi.bbox as [number, number, number, number]);
  return (
    <>
      <section className="stats-grid memory-stats">
        <article><span>Area</span><strong className="small">{String(memory.aoi.name ?? describeAoi(memory.aoi as never))}</strong><small>{Number(memory.aoi.area_km2).toLocaleString()} km²</small></article>
        <article><span>Record</span><strong className="small">{memory.period.start} → {memory.period.end}</strong><small>{memory.period.days.toLocaleString()} days</small></article>
        <article><span>Harmonized activity</span><strong>{Math.round(memory.summary.total_harmonized_activity).toLocaleString()}</strong><small>MODIS-equivalent active-cell days · {memory.summary.total_hotspots.toLocaleString()} raw detections</small></article>
        <article><span>Now vs history</span><strong className={`category ${cmp.overall_category?.replace(/\s/g, "-").toLowerCase()}`}>{cmp.overall_category ?? "Not assessed"}</strong><small>{cmp.robust_z !== undefined ? `robust z ${cmp.robust_z}` : cmp.note}</small></article>
      </section>

      <section className="memory-grid">
        <article className="viz-panel wide">
          <h3>Burning Activity Calendar</h3>
          <p className="meta-text">Monthly harmonized burning activity per year. Empty cells are outside the record.</p>
          <Plot
            data={[{ type: "heatmap", x: memory.calendar.months, y: memory.calendar.years.map(String), z: memory.calendar.activity, colorscale: "YlOrRd", reversescale: true, hovertemplate: "%{y} %{x}: %{z:.1f} active-cell days<extra></extra>", xgap: 2, ygap: 2 }]}
            layout={{ ...plotLayout, height: Math.max(220, 34 * memory.calendar.years.length + 80), margin: { l: 50, r: 10, t: 10, b: 30 }, yaxis: { autorange: "reversed", type: "category" } }}
            config={{ responsive: true, displayModeBar: false }}
            className="plot"
          />
        </article>

        <article className="viz-panel">
          <h3>Seasonal Fire Profile</h3>
          <p className="meta-text">
            Peak: <strong>{memory.seasonal_profile.peak_months.join(", ") || "none"}</strong> · Active: {memory.seasonal_profile.active_months.join(", ") || "none"} · Quiet: {memory.seasonal_profile.quiet_months.join(", ") || "none"}
          </p>
          <Plot
            data={[
              {
                type: "bar",
                x: memory.seasonal_profile.months.map((m) => m.name),
                y: memory.seasonal_profile.months.map((m) => m.median_activity ?? 0),
                marker: { color: memory.seasonal_profile.months.map((m) => SEASON_COLORS[m.season_level] ?? "#cbd5e1") },
                error_y: {
                  type: "data",
                  symmetric: false,
                  array: memory.seasonal_profile.months.map((m) => (m.activity_iqr ? m.activity_iqr[1] - (m.median_activity ?? 0) : 0)),
                  arrayminus: memory.seasonal_profile.months.map((m) => (m.activity_iqr ? (m.median_activity ?? 0) - m.activity_iqr[0] : 0)),
                  color: "#475569",
                },
                hovertemplate: "%{x}: median %{y:.1f}<extra></extra>",
              },
            ]}
            layout={{ ...plotLayout, height: 280, margin: { l: 50, r: 10, t: 10, b: 30 }, yaxis: { title: { text: "median monthly activity" } } }}
            config={{ responsive: true, displayModeBar: false }}
            className="plot"
          />
        </article>

        <article className="viz-panel">
          <h3>Current vs Historical</h3>
          {cmp.status === "ok" ? (
            <>
              <p className="meta-text">
                {cmp.window?.start} → {cmp.window?.end}, compared with the same window in {cmp.history_years?.length} earlier years. Current {cmp.current?.harmonized_activity} vs median{" "}
                {cmp.historical?.median_harmonized_activity}, higher than {cmp.percentile_rank}% of years.
              </p>
              {cmp.flags.length === 0 ? (
                <p className="empty-state">No unusual conditions flagged for this window.</p>
              ) : (
                <ul className="flag-list">
                  {cmp.flags.map((f) => (
                    <li key={f.flag}><strong>{f.label}</strong><span>{f.detail}</span></li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="empty-state">{cmp.note ?? "Not enough history for a comparison."}</p>
          )}
          <p className="meta-text">{cmp.note}</p>
        </article>

        <DailySeries memory={memory} />

        <article className="viz-panel wide">
          <h3>Seasonal statistics</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Month</th><th>Level</th><th>Median activity</th><th>Hotspots</th><th>Active days</th><th>Median FRP (MW)</th><th>Spread (10 km cells)</th><th>Event duration (h)</th><th>Events / yr</th><th>Share of year</th></tr>
              </thead>
              <tbody>
                {memory.seasonal_profile.months.map((m) => (
                  <tr key={m.month}>
                    <td>{m.name}</td>
                    <td><span className="season-pill" style={{ background: SEASON_COLORS[m.season_level] }}>{m.season_level}</span></td>
                    <td>{m.median_activity ?? "–"}</td>
                    <td>{m.median_hotspots ?? "–"}</td>
                    <td>{m.median_active_days ?? "–"}</td>
                    <td>{m.median_frp ?? "–"}</td>
                    <td>{m.median_spatial_spread_cells_10km ?? "–"}</td>
                    <td>{m.median_event_duration_hours ?? "–"}</td>
                    <td>{m.events_per_year ?? "–"}</td>
                    <td>{m.median_share_of_year !== undefined ? `${(m.median_share_of_year * 100).toFixed(1)}%` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <ChangePoints memory={memory} />

        <article className="viz-panel">
          <h3>Observation quality</h3>
          <p className="meta-text">Mean Observation Sufficiency Score {memory.observation_quality.mean_sufficiency_score}/100 · {memory.observation_quality.pct_days_unobservable}% of days unobservable (so "no fire" cannot be claimed).</p>
          <ul className="obs-list">
            {Object.entries(memory.observation_quality.counts).map(([key, count]) => (
              <li key={key}><span style={{ background: OBS_COLORS[key] }} />{memory.observation_quality.labels[key]}<strong>{count.toLocaleString()} days</strong></li>
            ))}
          </ul>
          <p className="meta-text">{memory.observation_quality.method}</p>
        </article>

        <article className="viz-panel">
          <h3>Sensor harmonization</h3>
          <dl className="kv">
            <div><dt>Status</dt><dd>{memory.calibration.status}</dd></div>
            <div><dt>VIIRS → MODIS factor</dt><dd>{memory.calibration.viirs_to_modis_factor ?? "not estimated"}</dd></div>
            <div><dt>Factor IQR</dt><dd>{memory.calibration.factor_iqr ? memory.calibration.factor_iqr.join(" – ") : "–"}</dd></div>
            <div><dt>Co-observed pairs</dt><dd>{memory.calibration.pairs}</dd></div>
          </dl>
          <p className="meta-text">{memory.calibration.note}</p>
          <p className="meta-text">Harmonized Observed Burning Activity is the best comparable estimate from the satellites. It is not ground truth.</p>
        </article>

        <article className="viz-panel wide">
          <h3>Critical periods</h3>
          <p className="meta-text">Runs of consecutive days with robust anomaly above 2 (Above Normal or higher).</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Start</th><th>End</th><th>Days</th><th>Max robust z</th><th>Total hotspots</th><th>Imagery</th></tr></thead>
              <tbody>
                {memory.critical_periods.map((p) => (
                  <tr key={`${p.start_date}-${p.end_date}`}>
                    <td>{p.start_date}</td><td>{p.end_date}</td><td>{p.duration_days}</td><td>{p.max_anomaly.toFixed(2)}</td><td>{p.total_hotspots}</td>
                    <td>{bbox && <WorldviewButton date={p.start_date} bbox={bbox} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="viz-panel wide provenance">
          <h3>Provenance</h3>
          <dl className="kv">
            {Object.entries(memory.provenance).filter(([k]) => k !== "failed_chunks").map(([k, v]) => (
              <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>
            ))}
          </dl>
        </article>
      </section>
    </>
  );
}

function DailySeries({ memory }: { memory: FireMemoryResult }) {
  const traces = useMemo(() => {
    const d = memory.daily;
    const x = d.map((r) => r.date);
    const flagged = d.filter((r) => r.anomaly_category !== "Normal" && !r.anomaly_category.startsWith("Not"));
    const unobservable = d.filter((r) => r.observation_status === "cloud_obscured" || r.observation_status === "missing_observation");
    return [
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.harmonized_high), line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.harmonized_low), fill: "tonexty", fillcolor: "rgba(234,88,12,0.18)", line: { width: 0 }, name: "uncertainty range", hoverinfo: "skip" },
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.harmonized_activity), line: { color: "#c2410c", width: 1.4 }, name: "harmonized activity", customdata: d.map((r) => [r.hotspot_count, r.modis_count, r.viirs_count, r.anomaly_category, r.observation_display, r.sufficiency_score]), hovertemplate: "%{x}<br>activity %{y:.2f}<br>detections %{customdata[0]} (MODIS %{customdata[1]}, VIIRS %{customdata[2]})<br>%{customdata[3]}<br>observation: %{customdata[4]} (%{customdata[5]}/100)<extra></extra>" },
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.baseline_median), line: { color: "#475569", width: 1, dash: "dot" }, name: "historical median" },
      { type: "scatter", mode: "markers", x: flagged.map((r) => r.date), y: flagged.map((r) => r.harmonized_activity), marker: { color: flagged.map((r) => CATEGORY_COLORS[r.anomaly_category]), size: 7 }, name: "anomaly", text: flagged.map((r) => r.anomaly_category), hovertemplate: "%{x}: %{text}<extra></extra>" },
      { type: "scatter", mode: "markers", x: unobservable.map((r) => r.date), y: unobservable.map(() => 0), marker: { symbol: "line-ns-open", color: "#64748b", size: 8 }, name: "UNKNOWN / insufficient observation", text: unobservable.map((r) => r.observation_display), hovertemplate: "%{x}: %{text}<extra></extra>" },
    ];
  }, [memory]);
  return (
    <article className="viz-panel wide">
      <h3>Harmonized daily activity and anomalies</h3>
      <p className="meta-text">MODIS-equivalent active ~1 km cells per day. Markers show Above Normal / Unusual / Highly Unusual days (robust median/MAD). Grey ticks mark days where absence of fire cannot be claimed.</p>
      <Plot
        data={traces as never}
        layout={{ ...plotLayout, height: 340, margin: { l: 50, r: 10, t: 10, b: 40 }, legend: { orientation: "h", y: -0.2 }, xaxis: { rangeslider: { visible: true } } }}
        config={{ responsive: true, displayModeBar: false }}
        className="plot"
      />
    </article>
  );
}

function ChangePoints({ memory }: { memory: FireMemoryResult }) {
  const cp = memory.change_points;
  const x = memory.monthly.map((m) => `${m.year}-${String(m.month).padStart(2, "0")}-01`);
  const shapes = cp.change_points.map((c) => ({ type: "line" as const, x0: `${c.date}-01`, x1: `${c.date}-01`, yref: "paper" as const, y0: 0, y1: 1, line: { color: "#7c3aed", width: 2, dash: "dash" as const } }));
  return (
    <article className="viz-panel wide">
      <h3>Long-term change points</h3>
      {cp.status !== "ok" ? (
        <p className="empty-state">{cp.note}</p>
      ) : (
        <>
          <Plot
            data={[{ type: "scatter", mode: "lines", x, y: memory.monthly.map((m) => m.harmonized_activity), line: { color: "#c2410c" }, name: "monthly activity" }]}
            layout={{ ...plotLayout, height: 240, margin: { l: 50, r: 10, t: 10, b: 30 }, shapes }}
            config={{ responsive: true, displayModeBar: false }}
            className="plot"
          />
          {cp.change_points.length === 0 ? (
            <p className="meta-text">No statistically detected change in the long-term level.</p>
          ) : (
            <ul className="flag-list">
              {cp.change_points.map((c) => <li key={c.date}><strong>{c.date}</strong><span>{c.description}</span></li>)}
            </ul>
          )}
          <p className="meta-text">{cp.method} {cp.caveat}</p>
        </>
      )}
    </article>
  );
}
