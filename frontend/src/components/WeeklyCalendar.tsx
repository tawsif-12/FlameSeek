import { useMemo, useState } from "react";
import Plot from "react-plotly.js";
import type { FireMemoryResult } from "../types/api";
import { FORECAST_WEEKS, MIN_BASELINE_YEARS, Z_THRESHOLD, buildCalendar, buildOutlook, weekDates, type WeekCell } from "../utils/weekly";

const plotLayout = { autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Inter, sans-serif", size: 12 } };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_WEEK = [1, 5, 9, 14, 18, 23, 27, 31, 36, 40, 44, 49];
const SEVERITY_COLOR = { Low: "#94a3b8", Moderate: "#f59e0b", High: "#ea580c", Severe: "#b91c1c" } as const;
type Tab = "Calendar" | "Anomalies" | "Forecast";

const dominant = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k.replace(/_/g, " ")} (${v} d)`).join(", ") || "none";

function Drawer({ cell, onClose }: { cell: WeekCell; onClose: () => void }) {
  const anomalous = cell.z !== null && cell.z >= Z_THRESHOLD;
  return (
    <aside className="week-drawer glass-card" aria-label={`Week ${cell.week} ${cell.year}`}>
      <button type="button" className="week-drawer-close" onClick={onClose} aria-label="Close">✕</button>
      <h4>Week {cell.week} · {cell.year}</h4>
      <p className="meta-text">{weekDates(cell.year, cell.week)} · {cell.days} day{cell.days > 1 ? "s" : ""} observed</p>
      <p><strong className={anomalous ? "category highly-unusual" : ""}>{cell.z === null ? `z-score not available (needs ${MIN_BASELINE_YEARS}+ earlier years)` : `z = ${cell.z >= 0 ? "+" : ""}${cell.z.toFixed(2)}${anomalous ? " · anomaly" : ""}`}</strong></p>
      <dl>
        <dt>Harmonized activity</dt><dd>{cell.activity.toFixed(1)}</dd>
        <dt>Harmonized FRP</dt><dd>{Math.round(cell.frp).toLocaleString()} MW</dd>
        <dt>Raw detections</dt><dd>{cell.hotspots.toLocaleString()} (MODIS {cell.modis}, VIIRS {cell.viirs})</dd>
        <dt>Active 0.01° cells</dt><dd>{cell.activeCells.toLocaleString()}</dd>
        {cell.mean !== null && <><dt>Baseline μ ± σ</dt><dd>{cell.mean.toFixed(1)} ± {(cell.sd ?? 0).toFixed(1)}</dd></>}
        <dt>Sensor agreement</dt><dd>{dominant(cell.agreement)}</dd>
        <dt>Observation quality</dt><dd>{dominant(cell.observation)}</dd>
      </dl>
      <small className="meta-text">Himawari persistence checks and the local-news attribution are not connected to this backend yet, so no cause label is shown.</small>
    </aside>
  );
}

export default function WeeklyCalendar({ memory }: { memory: FireMemoryResult }) {
  const cal = useMemo(() => buildCalendar(memory.daily), [memory]);
  const outlook = useMemo(() => buildOutlook(cal), [cal]);
  const [tab, setTab] = useState<Tab>("Calendar");
  const [metric, setMetric] = useState<"activity" | "frp">("activity");
  const [sel, setSel] = useState<WeekCell | null>(null);

  const z = cal.cells.map((row) => row.map((c) => (c ? c[metric] : null)));
  const text = cal.cells.map((row) => row.map((c) => (c ? `W${c.week} ${c.year}<br>activity ${c.activity.toFixed(1)} · FRP ${Math.round(c.frp)} MW${c.z !== null ? `<br>z ${c.z.toFixed(2)}` : ""}` : "no data")));
  const ax = cal.anomalies.filter((c) => cal.years.includes(c.year));
  const weeks = Array.from({ length: 52 }, (_, i) => i + 1);

  function onClick(ev: { points: Array<{ x?: unknown; y?: unknown }> }) {
    const p = ev.points[0];
    const yi = cal.years.indexOf(Number(p.y));
    const cell = yi >= 0 ? cal.cells[yi][Number(p.x) - 1] : null;
    if (cell) setSel(cell);
  }

  return (
    <section className="viz-panel wide weekly-calendar">
      <div className="weekly-tabs" role="tablist">
        {(["Calendar", "Anomalies", "Forecast"] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {t === "Forecast" ? "Predictive horizon" : t === "Anomalies" ? `Anomalies (${cal.anomalies.length})` : "52-week calendar"}
          </button>
        ))}
      </div>

      {tab === "Calendar" && (
        <>
          <p className="meta-text">
            One square is one week of one year, from the corrected (harmonized) record. Squares outlined in red are at least {Z_THRESHOLD.toFixed(1)} standard deviations above the average of the same week in earlier years. Click a square for details.
          </p>
          <div className="weekly-controls">
            <label><input type="radio" checked={metric === "activity"} onChange={() => setMetric("activity")} /> Fire activity</label>
            <label><input type="radio" checked={metric === "frp"} onChange={() => setMetric("frp")} /> Fire power (FRP)</label>
          </div>
          <div className="weekly-body">
            <Plot
              data={[
                { type: "heatmap", x: weeks, y: cal.years, z, text: text as never, hovertemplate: "%{text}<extra></extra>", colorscale: "YlOrRd", reversescale: true, xgap: 1, ygap: 1, hoverongaps: false, colorbar: { thickness: 10, title: { text: metric === "activity" ? "activity" : "MW" } } },
                { type: "scatter", mode: "markers", x: ax.map((c) => c.week), y: ax.map((c) => c.year), hoverinfo: "skip", marker: { symbol: "square-open", size: 11, color: "#b91c1c", line: { width: 1.6 } }, showlegend: false },
              ]}
              layout={{ ...plotLayout, height: Math.max(260, 22 * cal.years.length + 80), margin: { l: 50, r: 10, t: 10, b: 30 }, xaxis: { tickmode: "array", tickvals: MONTH_WEEK, ticktext: MONTHS, range: [0.5, 52.5] }, yaxis: { autorange: "reversed", type: "category" } }}
              config={{ responsive: true, displayModeBar: false }}
              className="plot"
              onClick={onClick}
            />
            {sel && <Drawer cell={sel} onClose={() => setSel(null)} />}
          </div>
        </>
      )}

      {tab === "Anomalies" && (
        <>
          <p className="meta-text">Weeks at z ≥ {Z_THRESHOLD.toFixed(1)}, using the rolling mean and standard deviation of the same calendar week in all earlier years (at least {MIN_BASELINE_YEARS}).</p>
          {cal.anomalies.length === 0 ? <p className="meta-text">No anomalous weeks in this period.</p> : (
            <table className="week-table">
              <thead><tr><th>Week</th><th>Dates</th><th>z</th><th>Activity</th><th>Baseline μ ± σ</th><th>Sensors</th></tr></thead>
              <tbody>
                {cal.anomalies.slice(0, 40).map((c) => (
                  <tr key={`${c.year}-${c.week}`} onClick={() => { setSel(c); setTab("Calendar"); }}>
                    <td>W{c.week} {c.year}</td><td>{weekDates(c.year, c.week)}</td><td>+{(c.z ?? 0).toFixed(2)}</td><td>{c.activity.toFixed(1)}</td><td>{(c.mean ?? 0).toFixed(1)} ± {(c.sd ?? 0).toFixed(1)}</td><td>{dominant(c.agreement)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {tab === "Forecast" && (
        outlook.weeks.length === 0 ? <p className="meta-text">At least {MIN_BASELINE_YEARS + 1} years of history are needed for an outlook. Run a longer look-back.</p> : (
          <>
            <p className="meta-text">
              Outlook for the next {FORECAST_WEEKS} weeks for the whole selected area: how often each upcoming week reached notable burning (activity ≥ {outlook.threshold.toFixed(1)}) in earlier years, adjusted by how far the last weeks ran above normal (average z = {outlook.lift >= 0 ? "+" : ""}{outlook.lift.toFixed(1)}).
              This is a recurrence baseline. It does not yet use weather covariates or a trained ConvLSTM/XGBoost model, and it is not a per-grid-cell forecast.
            </p>
            {outlook.peak && <p><strong>Expected peak: week {outlook.peak.week} ({weekDates(outlook.peak.year, outlook.peak.week).split(" – ")[0]}) · {outlook.peak.probability}% · {outlook.peak.severity} severity</strong></p>}
            <Plot
              data={[{ type: "bar", x: outlook.weeks.map((w) => `W${w.week}`), y: outlook.weeks.map((w) => w.probability), marker: { color: outlook.weeks.map((w) => SEVERITY_COLOR[w.severity]) }, text: outlook.weeks.map((w) => w.severity), hovertemplate: "%{x}: %{y}% · %{text}<extra></extra>" }]}
              layout={{ ...plotLayout, height: 280, margin: { l: 50, r: 10, t: 10, b: 40 }, yaxis: { title: { text: "Occurrence index (%)" }, range: [0, 100] } }}
              config={{ responsive: true, displayModeBar: false }}
              className="plot"
            />
          </>
        )
      )}
    </section>
  );
}
