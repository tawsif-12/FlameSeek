import { useEffect, useMemo, useState } from "react";
import Plot from "react-plotly.js";
import { useLocation, useNavigate } from "react-router-dom";
import { normalizeApiError, runJob, startFireMemory } from "../api/client";
import AnalysisNavigation from "../components/AnalysisNavigation";
import AOISelector from "../components/AOISelector";
import WorldviewButton from "../components/WorldviewButton";
import DataCoverageNotice from "../components/DataCoverageNotice";
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
type CalendarMode = "harmonized" | "raw" | "anomaly";

function medianOf(values: number[]) {
  if (!values.length) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function downloadFile(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvValue(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export default function FireMemoryPage() {
  const { aoi, sensors, setSensors, memory, setMemory } = useAppContext();
  const location = useLocation();
  const [years, setYears] = useState(5);
  const [windowDays, setWindowDays] = useState(30);
  const [job, setJob] = useState<Job<FireMemoryResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (location.pathname !== "/fire-calendar") return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById("fire-calendar")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.pathname, memory]);

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
      <AnalysisNavigation />
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="memory-intro nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Fire Memory</p>
          <h2>What normally happens in this area?</h2>
          <p className="lead">
            Pick a place and we look back through up to 26 years of NASA satellite records to show when it usually burns, how this year compares, and whether fires are becoming more or less common.
            Older and newer satellites see fires differently, so we first correct their records to make all years comparable.
          </p>
          <ul className="hero-chips">
            <li><span className="dot" />Up to 26 years</li>
            <li><span className="dot" />Four satellites, one fair record</li>
            <li><span className="dot" />Spots unusual years</li>
            <li><span className="dot" />Finds long-term changes</li>
          </ul>
        </header>
      </div>
      <DataCoverageNotice start={memory?.period.start} end={memory?.period.end} />
      <section className="memory-setup glass-card">
        <div className="memory-setup-map">
          <h3>1. Choose a place</h3>
          <AOISelector />
        </div>
        <div className="memory-setup-controls">
          <h3>2. How far back, and which satellites</h3>
          <label>
            How many years to look back
            <select value={years} onChange={(e) => setYears(Number(e.target.value))}>
              {[1, 2, 3, 5, 10, 15, 20, 26].map((y) => (
                <option key={y} value={y}>{y} year{y > 1 ? "s" : ""}{y >= 10 ? " (slow the first time)" : ""}</option>
              ))}
            </select>
          </label>
          <label>
            Compare the recent
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
            {running ? "Looking back through the records..." : "Show this place's fire history"}
          </button>
          {job && (
            <div className="job-progress" role="status">
              <div><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <small>{job.message}</small>
            </div>
          )}
          {error && (
            <div className="memory-error" role="alert">
              <p className="error-text">{error}</p>
              {error.includes("FIRMS_MAP_KEY") && <a href="https://firms.modaps.eosdis.nasa.gov/api/map_key/" target="_blank" rel="noreferrer">Get a free NASA FIRMS key ↗</a>}
            </div>
          )}
          <p className="meta-text">The first time for a place can take a few minutes, because the records are downloaded from NASA. After that the same place opens in about a second.</p>
        </div>
      </section>
      {!memory && (
        <section className="burning-calendar-placeholder glass-card" id="fire-calendar" aria-labelledby="burning-calendar-title">
          <p className="eyebrow"><span className="dot" /> Historical calendar</p>
          <h3 id="burning-calendar-title">Earth's Burning Calendar</h3>
          <p>Choose a place and select <strong>Show this place's fire history</strong>. Monthly satellite-observed burning activity will appear here.</p>
          <div className="calendar-placeholder-grid" aria-hidden="true">
            {Array.from({ length: 36 }, (_, index) => <span key={index} />)}
          </div>
        </section>
      )}
      {memory && <MemoryResults memory={memory} />}
    </main>
  );
}

const CATEGORY_PLAIN: Record<string, string> = {
  Normal: "About normal",
  "Above Normal": "More fire than usual",
  Unusual: "Unusually high",
  "Highly Unusual": "Far above usual",
};
const VERDICT_PLAIN: Record<string, string> = {
  "step removed": "Passed: the false jump is gone",
  "step reduced": "Partly: the false jump is smaller",
  "no improvement": "Not passed: the jump is still there",
};

function listWords(items: string[]) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

const OBS_PLAIN: Record<string, string> = {
  reliable_multi_sensor: "Fire seen by more than one type of satellite",
  valid_no_fire: "Clear view, no fire seen",
  limited_evidence: "Fire seen by only one type of satellite",
  sensor_disagreement: "Satellites disagreed",
  cloud_obscured: "Too cloudy to see",
  missing_observation: "No satellite passed over",
};

function MemorySummary({ memory }: { memory: FireMemoryResult }) {
  const profile = memory.seasonal_profile;
  const cmp = memory.current_vs_historical;
  const name = String(memory.aoi.name ?? "this place").split(",")[0];
  const step = (memory.witness.validation.continuity ?? []).find((c) => c.raw_count_ratio && c.consistent_record_ratio);
  const changes = memory.change_points.change_points ?? [];
  const quiet = profile.quiet_months.filter((m) => !profile.peak_months.includes(m) && !profile.active_months.includes(m));
  const now: Record<string, string> = {
    Normal: "Right now, fire activity is about normal for this time of year.",
    "Above Normal": "Right now, there is more fire than usual for this time of year.",
    Unusual: "Right now, fire activity is unusually high for this time of year.",
    "Highly Unusual": "Right now, fire activity is far above anything usual for this time of year.",
  };
  return (
    <section className="page-plain glass-card" aria-label="Summary in plain words">
      In {name}, fires are most common in {listWords(profile.peak_months) || "no particular month"}
      {quiet.length ? `, and rare in ${listWords(quiet.slice(0, 4))}${quiet.length > 4 ? " and other months" : ""}` : ""}.{" "}
      {now[cmp.overall_category ?? ""] ?? "There is not enough history yet to say whether this year is unusual."}{" "}
      {changes.length ? `Over the years, the level of fire ${changes[changes.length - 1].direction === "increase" ? "went up" : "went down"} around ${changes[changes.length - 1].date}.` : "Over these years, the overall level of fire has not clearly changed."}
      <small>
        Based on {memory.summary.total_hotspots.toLocaleString()} satellite fire sightings from {memory.period.start.slice(0, 4)} to {memory.period.end.slice(0, 4)}.
        {step ? ` When sharper satellites started in ${step.date.slice(0, 4)}, raw sightings became about ${Number(step.raw_count_ratio).toFixed(1)} times as many. That jump is not real: after our correction the record stays level.` : ""}
      </small>
    </section>
  );
}

function MemoryResults({ memory }: { memory: FireMemoryResult }) {
  const navigate = useNavigate();
  const [calendarMode, setCalendarMode] = useState<CalendarMode>("harmonized");
  const [selectedMonth, setSelectedMonth] = useState<{ year: number; month: number } | null>(null);
  const cmp = memory.current_vs_historical;
  const bbox = aoiBBox(memory.aoi as never) ?? (memory.aoi.bbox as [number, number, number, number]);
  const monthRows = useMemo(() => new Map(memory.monthly.map((row) => [`${row.year}-${row.month}`, row])), [memory]);
  const historicalMedian = (month: number, excludeYear: number) => medianOf(memory.monthly.filter((row) => row.month === month && row.year !== excludeYear && row.days_in_record >= 20).map((row) => row.harmonized_activity));
  const anomalyGrid = memory.calendar.years.map((year) => memory.calendar.months.map((_, index) => {
    const value = monthRows.get(`${year}-${index + 1}`)?.harmonized_activity;
    const baseline = historicalMedian(index + 1, year);
    return value === undefined || baseline === undefined || baseline <= 0 ? null : ((value - baseline) / baseline) * 100;
  }));
  const calendarGrid = calendarMode === "raw" ? memory.calendar.hotspots : calendarMode === "anomaly" ? anomalyGrid : memory.calendar.activity;
  const selectedRow = selectedMonth ? monthRows.get(`${selectedMonth.year}-${selectedMonth.month}`) : undefined;
  const selectedDays = selectedMonth ? memory.daily.filter((day) => day.date.startsWith(`${selectedMonth.year}-${String(selectedMonth.month).padStart(2, "0")}`)) : [];
  const selectedMedian = selectedMonth ? historicalMedian(selectedMonth.month, selectedMonth.year) : undefined;
  const selectedAnomaly = selectedRow && selectedMedian !== undefined && selectedMedian > 0 ? ((selectedRow.harmonized_activity - selectedMedian) / selectedMedian) * 100 : null;
  const lowCoverage = memory.monthly.filter((row) => row.mean_sufficiency < 50).map((row) => ({ x: memory.calendar.months[row.month - 1], y: String(row.year) }));
  const lowCoverageKeys = new Set(lowCoverage.map((point) => `${point.y}-${point.x}`));
  const calendarValues = calendarGrid.flat().filter((value): value is number => value !== null && Number.isFinite(value));
  const calendarScaleMax = Math.max(...calendarValues.map((value) => calendarMode === "anomaly" ? Math.abs(value) : value), 1);
  const calendarColors = ["#19344b", "#286682", "#5799a6", "#d9a050", "#f1743c", "#df4436"];
  const cellColor = (value: number) => {
    const ratio = calendarMode === "anomaly" ? (value + calendarScaleMax) / (2 * calendarScaleMax) : value / calendarScaleMax;
    return calendarColors[Math.min(calendarColors.length - 1, Math.max(0, Math.floor(Math.max(0, Math.min(1, ratio)) * calendarColors.length)))];
  };

  function exportCalendarCsv() {
    const header = ["aoi", "year", "month", "raw_detections", "harmonized_activity", "historical_median", "anomaly_pct", "uncertainty_low", "uncertainty_high", "days_in_record", "mean_sufficiency"];
    const rows = memory.monthly.map((row) => {
      const baseline = historicalMedian(row.month, row.year);
      const anomaly = baseline && baseline > 0 ? ((row.harmonized_activity - baseline) / baseline) * 100 : null;
      const daily = memory.daily.filter((day) => day.date.startsWith(`${row.year}-${String(row.month).padStart(2, "0")}`));
      return [String(memory.aoi.name ?? "Selected AOI"), row.year, memory.calendar.months[row.month - 1], row.hotspot_count, row.harmonized_activity, baseline ?? null, anomaly?.toFixed(2) ?? null, daily.reduce((sum, day) => sum + day.harmonized_low, 0).toFixed(2), daily.reduce((sum, day) => sum + day.harmonized_high, 0).toFixed(2), row.days_in_record, row.mean_sufficiency].map(csvValue).join(",");
    });
    const metadata = [`"# unit",${csvValue(memory.provenance.harmonized_unit)}`, `"# method",${csvValue(memory.provenance.harmonization)}`, `"# source","NASA FIRMS science archive"`];
    downloadFile("flameseek-fire-memory-calendar.csv", new Blob([[...metadata, header.map(csvValue).join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" }));
  }

  function exportCalendarPng() {
    const cellW = 70, cellH = 32, left = 75, top = 64;
    const canvas = document.createElement("canvas");
    canvas.width = left + cellW * 12 + 24;
    canvas.height = top + cellH * memory.calendar.years.length + 56;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.fillStyle = "#06101f"; context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#d8efff"; context.font = "bold 19px sans-serif"; context.fillText("FlameSeek · Fire Memory Calendar", 22, 28);
    context.fillStyle = "#7fa8c7"; context.font = "11px sans-serif"; context.fillText(String(memory.aoi.name ?? "Selected area"), 22, 47);
    const values = memory.calendar.activity.flat().filter((value): value is number => value !== null);
    const max = Math.max(...values, 1);
    memory.calendar.months.forEach((month, index) => context.fillText(month, left + index * cellW + 18, top - 10));
    memory.calendar.years.forEach((year, yearIndex) => {
      context.fillStyle = "#a7c7de"; context.fillText(String(year), 20, top + yearIndex * cellH + 20);
      memory.calendar.activity[yearIndex].forEach((value, monthIndex) => {
        const ratio = value === null ? -1 : Math.max(0, Math.min(1, value / max));
        context.fillStyle = ratio < 0 ? "#263143" : ratio < .25 ? "#0d3f63" : ratio < .5 ? "#08b8d8" : ratio < .75 ? "#ff9b32" : "#e33924";
        context.fillRect(left + monthIndex * cellW, top + yearIndex * cellH, cellW - 3, cellH - 3);
      });
    });
    context.fillStyle = "#7fa8c7"; context.fillText("NASA FIRMS · Aqua MODIS-equivalent activity per clear-sky look", 22, canvas.height - 18);
    canvas.toBlob((blob) => blob && downloadFile("flameseek-fire-memory-calendar.png", blob), "image/png");
  }
  return (
    <>
      <section className="memory-grid">
        <article className="viz-panel wide memory-calendar" id="fire-calendar">
          <header>
            <div>
              <p className="eyebrow">Earth's Burning Calendar</p>
              <h3>Monthly Burning Patterns</h3>
              <p className="meta-text">Each square is one month of one year. Click a square for its raw detections, corrected activity, historical median, anomaly, uncertainty and observation coverage.</p>
            </div>
            <span className="method-badge">Four-Witness consistent record</span>
          </header>
          <div className="memory-calendar-toolbar">
            <div role="group" aria-label="Calendar metric">
              <button className={calendarMode === "harmonized" ? "active" : ""} onClick={() => setCalendarMode("harmonized")}>Corrected activity</button>
              <button className={calendarMode === "raw" ? "active" : ""} onClick={() => setCalendarMode("raw")}>Raw detections</button>
              <button className={calendarMode === "anomaly" ? "active" : ""} onClick={() => setCalendarMode("anomaly")}>Relative anomaly</button>
            </div>
            <div><button onClick={exportCalendarCsv}>Download CSV</button><button onClick={exportCalendarPng}>Download PNG</button></div>
          </div>
          <div className="burning-pattern-scroll">
            <div className="burning-pattern-grid" role="grid" aria-label="Monthly burning patterns by year">
              <span className="calendar-corner" role="columnheader">Year</span>
              {memory.calendar.months.map((month) => <span className="calendar-month" role="columnheader" key={month}>{month}</span>)}
              {memory.calendar.years.map((year, yearIndex) => [
                <span className="calendar-year" role="rowheader" key={`${year}-label`}>{year}</span>,
                ...memory.calendar.months.map((month, monthIndex) => {
                  const value = calendarGrid[yearIndex][monthIndex];
                  const limited = lowCoverageKeys.has(`${year}-${month}`);
                  const label = value === null ? `${month} ${year}: missing observation` : `${month} ${year}: ${value.toFixed(1)}${calendarMode === "anomaly" ? "% from historical median" : calendarMode === "raw" ? " raw detections" : " corrected activity"}${limited ? ", low observation sufficiency" : ""}`;
                  return <button
                    type="button"
                    role="gridcell"
                    key={`${year}-${month}`}
                    className={`burning-month-cell${value === null ? " missing" : ""}${limited ? " limited" : ""}`}
                    style={value === null ? undefined : { backgroundColor: cellColor(value) }}
                    title={label}
                    aria-label={label}
                    onClick={() => setSelectedMonth({ year, month: monthIndex + 1 })}
                  >{limited && <span aria-hidden="true">×</span>}</button>;
                }),
              ])}
            </div>
          </div>
          <div className="burning-calendar-legend" aria-label="Activity color scale">
            <span>Lower activity</span><div>{calendarColors.map((color) => <i key={color} style={{ backgroundColor: color }} />)}</div><span>Higher activity</span>
          </div>
          <p className="calendar-legend-note"><span className="missing-swatch" /> Patterned grey = missing observation, not zero · <b>×</b> = observation sufficiency below 50/100. Anomaly uses the same month in other complete years, excluding the selected year.</p>
          {selectedMonth && <div className="memory-calendar-detail" aria-live="polite">
            <header><h4>{memory.calendar.months[selectedMonth.month - 1]} {selectedMonth.year}</h4><button aria-label="Close month details" onClick={() => setSelectedMonth(null)}>×</button></header>
            {selectedRow ? <>
              <dl>
                <div><dt>Raw detections</dt><dd>{selectedRow.hotspot_count.toLocaleString()}</dd></div>
                <div><dt>Corrected activity</dt><dd>{selectedRow.harmonized_activity.toFixed(2)}</dd></div>
                <div><dt>Historical median</dt><dd>{selectedMedian === undefined ? "Insufficient baseline" : selectedMedian.toFixed(2)}</dd></div>
                <div><dt>Anomaly</dt><dd>{selectedAnomaly === null ? (selectedMedian === 0 ? `Absolute difference ${selectedRow.harmonized_activity.toFixed(2)}; median is zero` : "Insufficient baseline") : `${selectedAnomaly >= 0 ? "+" : ""}${selectedAnomaly.toFixed(1)}%`}</dd></div>
                <div><dt>Uncertainty interval</dt><dd>{selectedDays.length ? `${selectedDays.reduce((sum, day) => sum + day.harmonized_low, 0).toFixed(2)}–${selectedDays.reduce((sum, day) => sum + day.harmonized_high, 0).toFixed(2)}` : "Not available"}</dd></div>
                <div><dt>Data coverage</dt><dd>{selectedRow.days_in_record} record days · sufficiency {selectedRow.mean_sufficiency.toFixed(0)}/100</dd></div>
                <div><dt>Sensor coverage</dt><dd>{selectedDays.reduce((sum, day) => sum + day.modis_count, 0)} MODIS · {selectedDays.reduce((sum, day) => sum + day.viirs_count, 0)} VIIRS</dd></div>
                <div><dt>Static-source filtering</dt><dd>Not applied; backend flagging is unavailable</dd></div>
              </dl>
              <button className="primary-button" onClick={() => navigate(`/fire-map?date=${selectedMonth.year}-${String(selectedMonth.month).padStart(2, "0")}-15&aoi=1&from=memory`)}>View Hotspots on Map</button>
              <small>The historical map loads one day at a time, so it opens the middle day of this month.</small>
            </> : <p className="empty-state">No observation record exists for this month; it is not treated as zero.</p>}
          </div>}
        </article>
      </section>

      <MemorySummary memory={memory} />
      <section className="stats-grid memory-stats">
        <article><span>Place</span><strong className="small">{String(memory.aoi.name ?? describeAoi(memory.aoi as never))}</strong><small>{Number(memory.aoi.area_km2).toLocaleString()} km²</small></article>
        <article><span>Requested period</span><strong className="small">{memory.period.start} → {memory.period.end}</strong><small>{memory.period.days.toLocaleString()} calendar days; daily coverage unverified</small></article>
        <article><span>Fire activity (corrected)</span><strong>{Math.round(memory.summary.total_harmonized_activity).toLocaleString()}</strong><small>fire sightings after correcting for satellite differences · {memory.summary.total_hotspots.toLocaleString()} raw sightings</small></article>
        <article><span>This year compared with usual</span><strong className={`category ${cmp.overall_category?.replace(/\s/g, "-").toLowerCase()}`}>{CATEGORY_PLAIN[cmp.overall_category ?? ""] ?? "Not enough data"}</strong><small>{cmp.robust_z !== undefined ? `unusualness score ${Number(cmp.robust_z).toFixed(1)} (above 2 is more than usual)` : cmp.note}</small></article>
      </section>

      <section className="memory-grid">

        <article className="viz-panel">
          <h3>The fire season</h3>
          <p className="meta-text">
            Most fire in <strong>{memory.seasonal_profile.peak_months.join(", ") || "no clear month"}</strong>. Some fire in {memory.seasonal_profile.active_months.join(", ") || "no other months"}. Almost none in {memory.seasonal_profile.quiet_months.join(", ") || "no months"}. Bars show a typical year; the thin lines show how much it varies.
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
            layout={{ ...plotLayout, height: 280, margin: { l: 50, r: 10, t: 10, b: 30 }, yaxis: { title: { text: "typical fire activity" } } }}
            config={{ responsive: true, displayModeBar: false }}
            className="plot"
          />
        </article>

        <article className="viz-panel">
          <h3>Is this year unusual?</h3>
          {cmp.status === "ok" ? (
            <>
              <p className="meta-text">
                From {cmp.window?.start} to {cmp.window?.end}, this place had more fire than {cmp.percentile_rank}% of the {cmp.history_years?.length} earlier years over the same dates (activity {cmp.current?.harmonized_activity} now,{" "}
                {cmp.historical?.median_harmonized_activity} in a typical year).
              </p>
              {cmp.flags.length === 0 ? (
                <p className="empty-state">Nothing unusual in this period.</p>
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
          <h3>Month-by-month numbers</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Month</th><th>Season</th><th>Typical activity</th><th>Sightings</th><th>Days with fire</th><th>Typical fire power (MW)</th><th>Area affected (10 km squares)</th><th>How long fires last (h)</th><th>Fires per year</th><th>Share of the year's fire</th></tr>
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
          <h3>How often could satellites see the ground?</h3>
          <p className="meta-text">On {memory.observation_quality.pct_days_unobservable}% of days, clouds or missing passes hid this place. On those days "no fire seen" does not mean "no fire". Average viewing score: {memory.observation_quality.mean_sufficiency_score} out of 100.</p>
          <ul className="obs-list">
            {Object.entries(memory.observation_quality.counts).map(([key, count]) => (
              <li key={key}><span style={{ background: OBS_COLORS[key] }} />{OBS_PLAIN[key] ?? memory.observation_quality.labels[key]}<strong>{count.toLocaleString()} days</strong></li>
            ))}
          </ul>
          <details className="tech"><summary>Technical details</summary><p className="meta-text">{memory.observation_quality.method}</p></details>
        </article>

        <FourWitness memory={memory} />

        <article className="viz-panel wide">
          <h3>Periods with unusually many fires</h3>
          <p className="meta-text">Stretches of days in a row with clearly more fire than normal for that time of year.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Start</th><th>End</th><th>Days</th><th>How unusual (score)</th><th>Fire sightings</th><th>Satellite picture</th></tr></thead>
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
          <h3>Where the data comes from</h3>
          <p className="meta-text">All fire sightings come from NASA's FIRMS service (MODIS and VIIRS satellite cameras). Cloud cover comes from the ERA5 weather record.</p>
          <details className="tech">
            <summary>Technical details</summary>
          <dl className="kv">
            {Object.entries(memory.provenance).filter(([k]) => k !== "failed_chunks").map(([k, v]) => (
              <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>
            ))}
          </dl>
          </details>
        </article>
      </section>
    </>
  );
}

const SENSOR_CHANGES = [
  { date: "2012-01-20", label: "Suomi NPP VIIRS" },
  { date: "2018-04-01", label: "NOAA-20 VIIRS" },
  { date: "2021-07-01", label: "Aqua drift" },
];

function FourWitness({ memory }: { memory: FireMemoryResult }) {
  const w = memory.witness;
  const profile = w.summary.detection_profile;
  const curve = w.summary.diurnal.overall;
  const hidden = w.validation.hide_one_witness;
  const monthly = useMemo(() => {
    const by = new Map<string, { raw: number; consistent: number; detailed: number; detailedDays: number }>();
    memory.daily.forEach((r) => {
      const key = r.date.slice(0, 7);
      const m = by.get(key) ?? { raw: 0, consistent: 0, detailed: 0, detailedDays: 0 };
      m.raw += r.hotspot_count;
      m.consistent += r.harmonized_activity;
      if (r.detailed_activity !== null) {
        m.detailed += r.detailed_activity;
        m.detailedDays += 1;
      }
      by.set(key, m);
    });
    const keys = [...by.keys()].sort();
    return { x: keys.map((k) => `${k}-01`), rows: keys.map((k) => by.get(k)!) };
  }, [memory]);
  const start = memory.daily[0]?.date ?? "";
  const end = memory.daily[memory.daily.length - 1]?.date ?? "";
  const shapes = SENSOR_CHANGES.filter((c) => c.date > start && c.date < end).map((c) => ({ type: "line" as const, x0: c.date, x1: c.date, yref: "paper" as const, y0: 0, y1: 1, line: { color: "#64748b", width: 1, dash: "dot" as const } }));
  const annotations = SENSOR_CHANGES.filter((c) => c.date > start && c.date < end).map((c) => ({ x: c.date, y: 1, yref: "paper" as const, text: c.label, showarrow: false, font: { size: 10, color: "#64748b" }, yanchor: "bottom" as const }));
  return (
    <>
      <article className="viz-panel">
        <h3>The satellites, and how well each one sees</h3>
        <p className="meta-text">Four satellites watch for fires. The newer VIIRS cameras are sharper and catch small fires that the older MODIS cameras miss, so their counts cannot simply be added together.</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Satellite</th><th>Fire sightings</th><th>Chance it spots a fire</th><th>Views per pass</th></tr></thead>
            <tbody>
              {Object.entries(w.summary.witnesses).filter(([, v]) => v.detections > 0).map(([k, v]) => (
                <tr key={k}><td>{v.label}</td><td>{v.detections.toLocaleString()}</td><td>{Math.round(v.sensitivity_per_look * 100)}%</td><td>{v.looks_per_pass_at_aoi}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="meta-text">Of the fires the sharper cameras saw here, the older cameras would have caught about <strong>{Math.round(w.summary.modis_fraction_of_viirs_fires * 100)}%</strong>. We use that to put every year on the same footing.</p>
        <details className="tech">
          <summary>Technical details</summary>
        <dl className="kv">
          <div><dt>Detection profile</dt><dd>{profile.source === "learned" ? `learned from ${profile.matchups.toLocaleString()} Aqua/S-NPP matchups` : "published prior"}</dd></div>
          <div><dt>MODIS 50% detection</dt><dd>{profile.frp50_nadir_mw ?? "–"} MW at nadir · {profile.frp50_scan_edge_mw ?? "–"} MW at scan edge</dd></div>
          <div><dt>VIIRS fires MODIS would see</dt><dd>{Math.round(w.summary.modis_fraction_of_viirs_fires * 100)}%</dd></div>
          <div><dt>MODIS / VIIRS FRP</dt><dd>{profile.modis_frp_per_viirs_frp} ({profile.frp_relation_source})</dd></div>
          <div><dt>MODIS duplicates removed</dt><dd>{(w.summary.cleaning.modis_duplicates_removed ?? 0).toLocaleString()}</dd></div>
          <div><dt>Daily fire curve</dt><dd>peak {curve.peak_hour.toFixed(1)} h local, width {curve.width_h} h ({w.summary.diurnal.source})</dd></div>
        </dl>
        <p className="meta-text">{profile.note}</p>
        <p className="meta-text">{w.summary.diurnal.note}</p>
        <p className="meta-text">{w.summary.effort.method} Cloud: {w.summary.effort.cloud_source}.</p>
        <p className="meta-text">{w.summary.fusion.method}</p>
        </details>
      </article>

      <article className="viz-panel wide">
        <h3>Why raw satellite counts are misleading</h3>
        <p className="meta-text">
          Grey bars: every fire sighting, counted as-is. They jump when a sharper satellite starts work (dotted lines), which looks like more fire but is only better eyesight. Orange line: our
          corrected record, which counts fires the same way in every year, so real changes stand out. Blue dashes: everything the sharper cameras see, used for the live map.
        </p>
        <Plot
          data={[
            { type: "bar", x: monthly.x, y: monthly.rows.map((m) => m.raw), name: "all sightings, uncorrected", marker: { color: "rgba(100,116,139,0.35)" }, yaxis: "y2" },
            { type: "scatter", mode: "lines", x: monthly.x, y: monthly.rows.map((m) => m.consistent), name: "corrected record (fair across years)", line: { color: "#c2410c", width: 2 } },
            { type: "scatter", mode: "lines", x: monthly.x, y: monthly.rows.map((m) => (m.detailedDays ? m.detailed : null)), name: "sharper cameras only", line: { color: "#0ea5e9", width: 1.2, dash: "dash" } },
          ] as never}
          layout={{
            ...plotLayout,
            height: 300,
            margin: { l: 50, r: 50, t: 24, b: 40 },
            legend: { orientation: "h", y: -0.18 },
            shapes,
            annotations,
            yaxis: { title: { text: "corrected activity" } },
            yaxis2: { overlaying: "y", side: "right", title: { text: "raw sightings" }, showgrid: false },
          }}
          config={{ responsive: true, displayModeBar: false }}
          className="plot"
        />
      </article>

      <article className="viz-panel wide">
        <h3>Did the correction work?</h3>
        <h4>Test 1: does the record stay level when a new satellite starts?</h4>
        {(w.validation.continuity ?? []).length === 0 ? (
          <p className="meta-text">This test needs at least a year of records before and after a new satellite started (January 2012 or April 2018). Choose a longer history to see it.</p>
        ) : (
          <ul className="flag-list">
            {(w.validation.continuity ?? []).map((c) => (
              <li key={c.change}>
                <strong>{VERDICT_PLAIN[c.verdict ?? ""] ?? "Not assessed"}</strong>
                <span>
                  When {c.change.replace(" start", "")} began in {c.date.slice(0, 4)}, raw sightings became about {c.raw_count_ratio ? Number(c.raw_count_ratio).toFixed(1) : "–"} times as many. Our corrected record changed by only ×{c.consistent_record_ratio ? Number(c.consistent_record_ratio).toFixed(2) : "–"} (1.00 would be perfectly level).
                </span>
              </li>
            ))}
          </ul>
        )}
        <h4>Test 2: can we predict what a hidden satellite saw?</h4>
        {hidden?.status === "ok" ? (
          <p className="meta-text">
            We hid {hidden.hidden} and tried to predict where it saw fire, using only the other satellites. Score: <strong>{hidden.auc_fused ?? "–"}</strong> out of 1 (0.5 would be pure guessing, 1 is perfect).
          </p>
        ) : null}
        <details className="tech">
          <summary>Technical details</summary>
        {hidden?.status === "ok" ? (
          <dl className="kv">
            <div><dt>Hidden</dt><dd>{hidden.hidden} ({hidden.hidden_detections?.toLocaleString()} detected cell-days)</dd></div>
            <div><dt>AUC, fused probability</dt><dd>{hidden.auc_fused ?? "–"}</dd></div>
            <div><dt>AUC, historical rate only</dt><dd>{hidden.auc_prior_only ?? "–"}</dd></div>
            <div><dt>AUC, hard cases</dt><dd>{hidden.auc_fused_where_other_witnesses_detected ?? "–"}</dd></div>
            <div><dt>Brier (fused vs prior)</dt><dd>{hidden.brier_fused} vs {hidden.brier_prior_only}</dd></div>
          </dl>
        ) : null}
        <p className="meta-text">{hidden?.note ?? "Not run."}</p>
        </details>
      </article>
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
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.harmonized_low), fill: "tonexty", fillcolor: "rgba(234,88,12,0.18)", line: { width: 0 }, name: "possible range", hoverinfo: "skip" },
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.harmonized_activity), line: { color: "#c2410c", width: 1.4 }, name: "fire activity (corrected)", customdata: d.map((r) => [r.hotspot_count, r.modis_count, r.viirs_count, r.anomaly_category, r.observation_display, r.sufficiency_score]), hovertemplate: "%{x}<br>activity %{y:.2f}<br>detections %{customdata[0]} (MODIS %{customdata[1]}, VIIRS %{customdata[2]})<br>%{customdata[3]}<br>observation: %{customdata[4]} (%{customdata[5]}/100)<extra></extra>" },
      { type: "scatter", mode: "lines", x, y: d.map((r) => r.baseline_median), line: { color: "#475569", width: 1, dash: "dot" }, name: "usual for this time of year" },
      { type: "scatter", mode: "markers", x: flagged.map((r) => r.date), y: flagged.map((r) => r.harmonized_activity), marker: { color: flagged.map((r) => CATEGORY_COLORS[r.anomaly_category]), size: 7 }, name: "unusually many fires", text: flagged.map((r) => r.anomaly_category), hovertemplate: "%{x}: %{text}<extra></extra>" },
      { type: "scatter", mode: "markers", x: unobservable.map((r) => r.date), y: unobservable.map(() => 0), marker: { symbol: "line-ns-open", color: "#64748b", size: 8 }, name: "clouds hid the ground", text: unobservable.map((r) => r.observation_display), hovertemplate: "%{x}: %{text}<extra></extra>" },
    ];
  }, [memory]);
  return (
    <article className="viz-panel wide">
      <h3>Fire activity, day by day</h3>
      <p className="meta-text">Orange line: fire activity each day, counted the same way for every satellite. Dotted line: what is usual for that time of year. Coloured dots: days with clearly more fire than usual. Grey ticks: days when clouds hid the ground, so we cannot say there was no fire.</p>
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
      <h3>Has fire activity changed over the years?</h3>
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
            <p className="meta-text">No lasting change found: fire activity has stayed at about the same level over these years.</p>
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
