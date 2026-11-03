import { useEffect, useMemo, useRef, useState } from "react";
import Plot from "react-plotly.js";
import { Link, useNavigate } from "react-router-dom";
import { normalizeApiError, runJob, searchPlaces, startFireMemory } from "../api/client";
import AOISelector from "../components/AOISelector";
import AnalysisNavigation from "../components/AnalysisNavigation";
import FireDnaEmptyDashboard from "../components/FireDnaEmptyDashboard";
import FireDnaFingerprint from "../components/FireDnaFingerprint";
import { DEFAULT_SENSORS, SENSOR_LABELS, describeAoi, useAppContext } from "../context/AppContext";
import type { FireMemoryResult, Job, SensorName } from "../types/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const plotLayout = { autosize: true, paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#8fb0c9", family: "Inter, sans-serif", size: 11 } };

function median(values: number[]) {
  if (!values.length) return undefined;
  const ordered = [...values].sort((a, b) => a - b), middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}
function download(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}
function quote(value: unknown) { return `"${String(value ?? "").replace(/"/g, '""')}"`; }

export default function FireDnaPage() {
  const { aoi, setAoi, sensors, setSensors, memory, setMemory } = useAppContext();
  const navigate = useNavigate();
  const [years, setYears] = useState(5);
  const [job, setJob] = useState<Job<FireMemoryResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getUTCMonth() + 1);
  const [showMeaning, setShowMeaning] = useState(false);
  const running = job?.status === "queued" || job?.status === "running";
  const profile = memory?.fire_dna;

  async function analyze() {
    if (!aoi) return;
    setError(null);
    try {
      const result = await runJob(startFireMemory(aoi, years, sensors, 30), setJob);
      setMemory(result);
      const comparableYears = result.fire_dna.annual.filter((row) => row.comparable);
      setSelectedYear(comparableYears[comparableYears.length - 1]?.year ?? result.calendar.years[result.calendar.years.length - 1] ?? null);
      const peak = result.fire_dna.monthly_reference.find((row) => row.name === result.fire_dna.peak_month);
      if (peak) setSelectedMonth(peak.month);
    } catch (reason) { setError(normalizeApiError(reason)); }
    finally { setJob(null); }
  }

  const defaultRegionStarted = useRef(false);
  useEffect(() => {
    if (aoi || memory || defaultRegionStarted.current) return;
    defaultRegionStarted.current = true;
    searchPlaces("Bangladesh")
      .then(([place]) => {
        if (!place) throw new Error("Bangladesh boundary was not found");
        setAoi({ geometry: place.geometry, bbox: place.bbox, name: "Bangladesh", kind: "place" });
      })
      .catch(() => setAoi({ bbox: [88.007915, 20.3679092, 92.679956, 26.635823], name: "Bangladesh", kind: "place" }));
  }, [aoi, memory, setAoi]);

  const selectedYearRows = memory && selectedYear ? memory.monthly.filter((row) => row.year === selectedYear) : [];
  const selectedRow = selectedYearRows.find((row) => row.month === selectedMonth);
  const baselineValues = memory && selectedYear ? memory.monthly.filter((row) => row.month === selectedMonth && row.year !== selectedYear && row.days_in_record >= 20).map((row) => row.harmonized_activity) : [];
  const baseline = median(baselineValues);
  const deviations = baseline === undefined ? [] : baselineValues.map((value) => Math.abs(value - baseline));
  const mad = median(deviations);
  const robustZ = selectedRow && baseline !== undefined && mad !== undefined && mad > 0 ? (selectedRow.harmonized_activity - baseline) / (1.4826 * mad) : null;
  const anomalyPct = selectedRow && baseline !== undefined && baseline > 0 ? 100 * (selectedRow.harmonized_activity - baseline) / baseline : null;
  const anomalyCategory = !selectedRow || baselineValues.length < 3 ? "Insufficient evidence" : robustZ === null ? "Within typical range" : robustZ >= 3.5 ? "Unusually high activity" : robustZ >= 2 ? "Elevated activity" : robustZ <= -2 ? "Unusually low activity" : "Within typical range";
  const annualSelected = profile?.annual.find((row) => row.year === selectedYear);
  const regionName = memory ? String(memory.aoi.name ?? describeAoi(memory.aoi as never)) : aoi ? describeAoi(aoi) : "Selected region";
  const selectedSummary = profile && selectedYear && selectedRow
    ? `${profile.summary} In ${MONTHS[selectedMonth - 1]} ${selectedYear}, activity was ${anomalyPct === null ? "not percentage-comparable with" : `${Math.abs(anomalyPct).toFixed(0)}% ${anomalyPct >= 0 ? "above" : "below"}`} the same-month historical median and was classified as ${anomalyCategory.toLowerCase()}.`
    : profile?.summary;

  function setMode(mode: "modis" | "viirs" | "harmonized") {
    setSensors(mode === "modis" ? ["modis"] : mode === "viirs" ? ["viirs_snpp", "viirs_noaa20", "viirs_noaa21"] : DEFAULT_SENSORS);
  }
  function exportCsv() {
    if (!profile || !memory) return;
    const lines = [["region", regionName], ["period", `${memory.period.start} to ${memory.period.end}`], ["unit", memory.provenance.harmonized_unit], ["method", profile.method]].map((row) => row.map(quote).join(","));
    lines.push(["record_type", "year_or_month", "activity", "q1", "q3", "comparable"].map(quote).join(","));
    profile.monthly_reference.forEach((row) => lines.push(["monthly_reference", row.name, row.median_activity, row.q1_activity, row.q3_activity, row.years >= 3].map(quote).join(",")));
    profile.annual.forEach((row) => lines.push(["annual", row.year, row.activity, "", "", row.comparable].map(quote).join(",")));
    download("flameseek-fire-dna.csv", new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  }
  function exportPng() {
    if (!profile) return;
    const canvas = document.createElement("canvas"); canvas.width = 900; canvas.height = 560;
    const context = canvas.getContext("2d"); if (!context) return;
    context.fillStyle = "#06101c"; context.fillRect(0, 0, 900, 560);
    context.fillStyle = "#e9f7ff"; context.font = "bold 30px sans-serif"; context.fillText("FlameSeek · Fire DNA Profile", 42, 52);
    context.fillStyle = "#7ea3bb"; context.font = "16px sans-serif"; context.fillText(regionName, 42, 82);
    const values = profile.monthly_reference.map((row) => row.median_activity ?? 0), max = Math.max(...values, 1), baseY = 440;
    values.forEach((value, index) => { const height = 280 * value / max; context.fillStyle = value / max > .7 ? "#ff5c35" : value / max > .35 ? "#ff9f43" : "#35c9df"; context.fillRect(52 + index * 68, baseY - height, 48, height); context.fillStyle = "#a9c4d6"; context.fillText(MONTHS[index], 58 + index * 68, baseY + 26); });
    context.fillStyle = "#7596aa"; context.font = "13px sans-serif"; context.fillText("Typical harmonized activity · NASA FIRMS · Four-Witness consistent record", 42, 520);
    canvas.toBlob((blob) => blob && download("flameseek-fire-dna.png", blob), "image/png");
  }
  function exportSummary() {
    if (!memory || !profile) return;
    const text = `FLAMESEEK FIRE DNA PROFILE\n\nRegion: ${regionName}\nHistorical period: ${memory.period.start} to ${memory.period.end}\nSource: NASA FIRMS MODIS/VIIRS\nUnit: ${memory.provenance.harmonized_unit}\n\n${selectedSummary}\n\nMethod: ${profile.method}\nTrend: ${profile.trend.method}\nGenerated: ${new Date().toISOString()}\n`;
    download("flameseek-fire-dna-summary.txt", new Blob([text], { type: "text/plain;charset=utf-8" }));
  }

  const trendColor = profile?.trend.direction === "Increasing" ? "#ff653d" : profile?.trend.direction === "Decreasing" ? "#55d8ef" : "#f0b45b";
  return <main className="fire-dna-page space-shell">
    <AnalysisNavigation />
    <section className="dna-hero"><div><p className="eyebrow">Global Fire Intelligence</p><h2>FIRE DNA PROFILE</h2><h1>Every Region Has a Fire History.</h1><p>Discover the unique seasonal patterns, historical trends, and unusual burning activity of any selected region.</p><small>Fire DNA summarizes patterns in satellite-detected hotspot activity. It does not determine the cause of every fire.</small></div><aside className="dna-hero-region"><span>◎</span><div><strong>{regionName}</strong><small>{memory ? "Analyzed fire-observation boundary" : "Select an area to begin"}</small></div></aside></section>

    <section className="dna-workspace">
      <article className="dna-panel dna-selector"><header><b>1.</b><h3>Select Region & Analysis Period</h3></header><div className="dna-selector-grid"><AOISelector /><div className="dna-controls"><label>Analysis period<select value={years} onChange={(event) => setYears(Number(event.target.value))}>{[3, 5, 10, 15, 20, 26].map((value) => <option value={value} key={value}>{value} years</option>)}</select></label><div className="dna-mode"><button onClick={() => setMode("harmonized")}>Harmonized</button><button onClick={() => setMode("modis")}>MODIS</button><button onClick={() => setMode("viirs")}>VIIRS</button></div><div className="dna-sensors">{DEFAULT_SENSORS.map((sensor: SensorName) => <label key={sensor}><input type="checkbox" checked={sensors.includes(sensor)} onChange={() => setSensors(sensors.includes(sensor) ? sensors.filter((item) => item !== sensor) : [...sensors, sensor])} />{SENSOR_LABELS[sensor]}</label>)}</div><p>Raw MODIS and VIIRS counts are not directly comparable. Harmonized mode corrects sensitivity, observation effort and time-of-day differences.</p><button className="dna-run" disabled={!aoi || !sensors.length || running} onClick={analyze}>{running ? "Building Fire DNA…" : "Generate Fire DNA Profile"}</button>{job && <div className="dna-progress"><i style={{ width: `${job.progress * 100}%` }} /><span>{job.message}</span></div>}{error && <p className="dna-error">{error}</p>}</div></div></article>

      {!profile && <FireDnaEmptyDashboard regionName={regionName} running={running} />}
      {profile && memory && <>
        <section className="dna-identity-row">
          <article className="dna-panel dna-identity"><header><b>2.</b><h3>Regional Fire Identity</h3></header><div className="dna-region-title"><span>🔥</span><div><strong>{regionName}</strong><small>{memory.period.start} → {memory.period.end}</small></div></div><div className="dna-metric-grid"><div><small>Peak burning month</small><strong>{profile.peak_month ?? "No stable peak"}</strong></div><div><small>Peak burning season</small><strong>{profile.peak_season.join("–") || "No stable season"}</strong></div><div><small>Typical annual activity</small><strong>{profile.typical_annual_activity?.toLocaleString() ?? "Insufficient data"}</strong><em>Aqua-equivalent / clear-sky look</em></div><div><small>Long-term trend</small><strong style={{ color: trendColor }}>{profile.trend.direction}</strong><em>{profile.trend.percent_per_year === null ? profile.trend.years + " complete years" : `${profile.trend.percent_per_year >= 0 ? "+" : ""}${profile.trend.percent_per_year.toFixed(1)}% per year`}</em></div></div></article>
          <article className="dna-panel"><FireDnaFingerprint profile={profile} /></article>
        </section>

        <section className="dna-chart-row">
          <article className="dna-panel"><header><b>3.</b><h3>Seasonal Fire Pattern</h3><select value={selectedYear ?? ""} onChange={(event) => setSelectedYear(Number(event.target.value))}><option value="">Reference only</option>{memory.calendar.years.map((year) => <option key={year}>{year}</option>)}</select></header><Plot data={[{ type: "bar", x: MONTHS, y: profile.monthly_reference.map((row) => row.median_activity), marker: { color: profile.monthly_reference.map((row) => row.name === profile.peak_month ? "#ff5b35" : "#27c5df") }, error_y: { type: "data", symmetric: false, array: profile.monthly_reference.map((row) => row.q3_activity === null || row.median_activity === null ? 0 : row.q3_activity - row.median_activity), arrayminus: profile.monthly_reference.map((row) => row.q1_activity === null || row.median_activity === null ? 0 : row.median_activity - row.q1_activity), color: "#9ed8e6" }, name: "Historical median", hovertemplate: "%{x}: %{y:.1f}<extra>Historical median</extra>" }, ...(selectedYear ? [{ type: "scatter" as const, mode: "lines+markers" as const, x: MONTHS, y: MONTHS.map((_, index) => selectedYearRows.find((row) => row.month === index + 1)?.harmonized_activity ?? null), line: { color: "#ffd166", width: 2 }, marker: { size: 6 }, name: String(selectedYear), hovertemplate: "%{x}: %{y:.1f}<extra>Selected year</extra>" }] : [])]} layout={{ ...plotLayout, height: 290, margin: { l: 52, r: 15, t: 25, b: 38 }, yaxis: { title: { text: "Harmonized activity" }, gridcolor: "rgba(90,160,200,.12)" }, xaxis: { gridcolor: "rgba(90,160,200,.08)" }, legend: { orientation: "h", y: 1.12 } }} config={{ responsive: true, displayModeBar: false }} className="plot" /><p className="dna-interpretation">{profile.peak_month ? `${profile.peak_month} has the highest typical satellite hotspot activity in ${regionName}.` : "There is not enough comparable history to identify a peak month."}</p></article>
          <article className="dna-panel"><header><b>4.</b><h3>Historical Fire Behaviour</h3><span className="dna-pill">Harmonized</span></header><Plot data={[{ type: "scatter", mode: "lines+markers", x: profile.annual.map((row) => row.year), y: profile.annual.map((row) => row.comparable ? row.activity : null), line: { color: "#ff6638", width: 2 }, marker: { color: "#ff8b42", size: 6 }, fill: "tozeroy", fillcolor: "rgba(255,90,45,.08)", connectgaps: false, hovertemplate: "%{x}: %{y:.1f}<extra>Complete year</extra>" }]} layout={{ ...plotLayout, height: 245, margin: { l: 52, r: 15, t: 18, b: 38 }, yaxis: { title: { text: "Harmonized activity" }, gridcolor: "rgba(90,160,200,.12)" }, xaxis: { gridcolor: "rgba(90,160,200,.08)" } }} config={{ responsive: true, displayModeBar: false }} className="plot" /><div className="dna-history-stats"><div><small>Highest activity year</small><strong>{profile.highest_year?.year ?? "—"}</strong><em>{profile.highest_year?.activity.toLocaleString() ?? "No complete year"}</em></div><div><small>Lowest activity year</small><strong>{profile.lowest_year?.year ?? "—"}</strong><em>{profile.lowest_year?.activity.toLocaleString() ?? "No complete year"}</em></div><div><small>Typical annual activity</small><strong>{profile.typical_annual_activity?.toLocaleString() ?? "—"}</strong><em>median</em></div><div><small>Long-term trend</small><strong style={{ color: trendColor }}>{profile.trend.direction}</strong><em>{profile.trend.slope_per_year?.toFixed(1) ?? "—"} units/year</em></div></div><p className="dna-method">{profile.trend.method}</p></article>
        </section>

        <section className="dna-analysis-row">
          <article className="dna-panel"><header><b>5.</b><h3>Unusual Burning Activity</h3></header><div className="dna-anomaly-controls"><select value={selectedYear ?? ""} onChange={(event) => setSelectedYear(Number(event.target.value))}>{memory.calendar.years.map((year) => <option key={year}>{year}</option>)}</select><select value={selectedMonth} onChange={(event) => setSelectedMonth(Number(event.target.value))}>{MONTHS.map((month, index) => <option value={index + 1} key={month}>{month}</option>)}</select></div><div className="dna-anomaly-table"><span>Selected activity<strong>{selectedRow?.harmonized_activity.toFixed(1) ?? "Missing"}</strong></span><span>Historical median<strong>{baseline?.toFixed(1) ?? "Unavailable"}</strong></span><span>Absolute difference<strong>{selectedRow && baseline !== undefined ? `${selectedRow.harmonized_activity - baseline >= 0 ? "+" : ""}${(selectedRow.harmonized_activity - baseline).toFixed(1)}` : "—"}</strong></span><span>Anomaly<strong>{anomalyPct === null ? baseline === 0 && selectedRow ? `+${selectedRow.harmonized_activity.toFixed(1)} absolute` : "Unavailable" : `${anomalyPct >= 0 ? "+" : ""}${anomalyPct.toFixed(0)}%`}</strong></span><span>Robust score<strong>{robustZ?.toFixed(2) ?? "Unavailable"}</strong></span><span>Status<strong className={anomalyCategory.includes("high") ? "hot" : anomalyCategory.includes("low") ? "cool" : ""}>{anomalyCategory}</strong></span></div><p className="dna-method">MAD-based robust score; ±2 marks elevated/low activity and +3.5 marks unusually high activity. At least three comparable baseline years are required.</p></article>
          <article className="dna-panel dna-selected"><header><b>6.</b><h3>Selected Period Analysis</h3></header><dl><div><dt>Period</dt><dd>{MONTHS[selectedMonth - 1]} {selectedYear}</dd></div><div><dt>Annual coverage</dt><dd>{annualSelected?.months ?? 0}/12 complete months</dd></div><div><dt>Confidence interval</dt><dd>{profile.monthly_reference[selectedMonth - 1]?.q1_activity?.toFixed(1) ?? "—"}–{profile.monthly_reference[selectedMonth - 1]?.q3_activity?.toFixed(1) ?? "—"}</dd></div><div><dt>Data coverage</dt><dd>{selectedRow?.days_in_record ?? 0} record days · {selectedRow?.mean_sufficiency.toFixed(0) ?? "—"}/100 sufficiency</dd></div><div><dt>Anomaly category</dt><dd className="hot">{anomalyCategory}</dd></div></dl><button onClick={() => navigate(`/fire-map?date=${selectedYear}-${String(selectedMonth).padStart(2, "0")}-15&aoi=1&from=dna`)}>⌖ View Hotspots on Map</button></article>
        </section>

        <section className="dna-summary-row"><article className="dna-panel dna-summary"><header><b>7.</b><h3>Fire DNA Summary</h3></header><p>{selectedSummary}</p><button onClick={() => setShowMeaning(!showMeaning)}>💡 What does this mean? <span>{showMeaning ? "−" : "+"}</span></button>{showMeaning && <div className="dna-meaning">This describes recurring satellite hotspot patterns, not the cause or number of individual fires. “Harmonized activity” corrects known differences between MODIS and VIIRS and observation opportunities. Missing or cloudy observations are not treated as zero activity.</div>}</article></section>

        <section className="dna-panel dna-reliability"><header><b>8.</b><h3>Data Reliability & Export</h3></header><div><span><small>Data source</small><strong>NASA FIRMS MODIS + VIIRS</strong></span><span><small>Observation period</small><strong>{memory.period.start.slice(0, 4)}–{memory.period.end.slice(0, 4)}</strong></span><span><small>Data coverage</small><strong>{profile.reliability.mean_sufficiency_score.toFixed(0)}/100 · {profile.reliability.label}</strong></span><span><small>Unobservable days</small><strong>{profile.reliability.pct_days_unobservable.toFixed(1)}%</strong></span><span><small>Static-source filtering</small><strong>Unavailable · not applied</strong></span></div><nav><button onClick={exportCsv}>⇩ Download CSV</button><button onClick={exportPng}>▣ Download PNG</button><button onClick={exportSummary}>≡ Download Summary</button></nav><footer>{profile.method} <Link to="/data-sources">Full methodology →</Link></footer></section>
      </>}
    </section>
  </main>;
}
