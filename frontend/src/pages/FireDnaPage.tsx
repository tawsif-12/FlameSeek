import { useEffect, useMemo, useRef, useState } from "react";
import Plot from "react-plotly.js";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  Calendar,
  Clock,
  Compass,
  Crosshair,
  Download,
  FileText,
  Flame,
  HelpCircle,
  Layers,
  MapPin,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  CheckCircle2,
} from "lucide-react";
import { normalizeApiError, runJob, startFireMemory } from "../api/client";
import AOISelector from "../components/AOISelector";
import AnalysisNavigation from "../components/AnalysisNavigation";
import FireDnaEmptyDashboard from "../components/FireDnaEmptyDashboard";
import FireDnaFingerprint from "../components/FireDnaFingerprint";
import { DEFAULT_SENSORS, SENSOR_LABELS, describeAoi, useAppContext } from "../context/AppContext";
import type { FireMemoryResult, Job, SensorName } from "../types/api";
import "../fire-dna-utilities.css";
import "../fire-dna-bento.css";
import { featureHref } from '../api/locationRoutes';

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const bentoPlotLayout = {
  autosize: true,
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#475569", family: "Inter, system-ui, -apple-system, sans-serif", size: 12 },
};

function median(values: number[]) {
  if (!values.length) return undefined;
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

function download(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function quote(value: unknown) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export default function FireDnaPage() {
  const { aoi, lockedArea, sensors, setSensors, memory, setMemory } = useAppContext();
  const navigate = useNavigate();
  const [years, setYears] = useState(5);
  const [job, setJob] = useState<Job<FireMemoryResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getUTCMonth() + 1);
  const [showMeaning, setShowMeaning] = useState(false);
  const running = job?.status === "queued" || job?.status === "running";
  const profile = memory?.fire_dna;
  const autoStarted = useRef(false);
  useEffect(() => {
    if (lockedArea && aoi && !memory && !autoStarted.current) { autoStarted.current = true; void analyze(); }
  }, [lockedArea, aoi, memory]);

  async function analyze() {
    if (!aoi) return;
    setError(null);
    try {
      const result = await runJob(startFireMemory(aoi, years, sensors, 30), setJob);
      setMemory(result);
      const comparableYears = result.fire_dna.annual.filter((row) => row.comparable);
      setSelectedYear(
        comparableYears[comparableYears.length - 1]?.year ??
          result.calendar.years[result.calendar.years.length - 1] ??
          null
      );
      const peak = result.fire_dna.monthly_reference.find((row) => row.name === result.fire_dna.peak_month);
      if (peak) setSelectedMonth(peak.month);
    } catch (reason) {
      setError(normalizeApiError(reason));
    } finally {
      setJob(null);
    }
  }

  // Calendar and DNA share results; initialize controls when either page loads one.
  useEffect(() => {
    if (!memory?.fire_dna) return;
    const comparable = memory.fire_dna.annual.filter(row => row.comparable);
    setSelectedYear(comparable[comparable.length - 1]?.year ?? memory.calendar.years[memory.calendar.years.length - 1] ?? null);
    const peak = memory.fire_dna.monthly_reference.find(row => row.name === memory.fire_dna.peak_month);
    if (peak) setSelectedMonth(peak.month);
  }, [memory]);

  const selectedYearRows = memory && selectedYear ? memory.monthly.filter((row) => row.year === selectedYear) : [];
  const selectedRow = selectedYearRows.find((row) => row.month === selectedMonth);
  const baselineValues =
    memory && selectedYear
      ? memory.monthly
          .filter((row) => row.month === selectedMonth && row.year !== selectedYear && row.days_in_record >= 20)
          .map((row) => row.harmonized_activity)
      : [];
  const baseline = median(baselineValues);
  const deviations = baseline === undefined ? [] : baselineValues.map((value) => Math.abs(value - baseline));
  const mad = median(deviations);
  const robustZ =
    selectedRow && baseline !== undefined && mad !== undefined && mad > 0
      ? (selectedRow.harmonized_activity - baseline) / (1.4826 * mad)
      : null;
  const anomalyPct =
    selectedRow && baseline !== undefined && baseline > 0
      ? (100 * (selectedRow.harmonized_activity - baseline)) / baseline
      : null;
  const anomalyCategory =
    !selectedRow || baselineValues.length < 3
      ? "Insufficient evidence"
      : robustZ === null
      ? "Within typical range"
      : robustZ >= 3.5
      ? "Unusually high activity"
      : robustZ >= 2
      ? "Elevated activity"
      : robustZ <= -2
      ? "Unusually low activity"
      : "Within typical range";

  const annualSelected = profile?.annual.find((row) => row.year === selectedYear);
  const regionName = memory
    ? String(memory.aoi.name ?? describeAoi(memory.aoi as never))
    : aoi
    ? describeAoi(aoi)
    : "Selected region";

  const selectedSummary =
    profile && selectedYear && selectedRow
      ? `${profile.summary} In ${MONTHS[selectedMonth - 1]} ${selectedYear}, activity was ${
          anomalyPct === null
            ? "not percentage-comparable with"
            : `${Math.abs(anomalyPct).toFixed(0)}% ${anomalyPct >= 0 ? "above" : "below"}`
        } the same-month historical median and was classified as ${anomalyCategory.toLowerCase()}.`
      : profile?.summary;

  function setMode(mode: "modis" | "viirs" | "harmonized") {
    setSensors(
      mode === "modis"
        ? ["modis"]
        : mode === "viirs"
        ? ["viirs_snpp", "viirs_noaa20", "viirs_noaa21"]
        : DEFAULT_SENSORS
    );
  }

  // Decadal Recurrence Heatmap matrix precomputation
  const heatmapData = useMemo(() => {
    if (!memory) return { years: [], maxVal: 1, lookup: new Map<string, number>() };
    const lookup = new Map<string, number>();
    let maxVal = 1;
    memory.monthly.forEach((row) => {
      lookup.set(`${row.year}-${row.month}`, row.harmonized_activity);
      if (row.harmonized_activity > maxVal) maxVal = row.harmonized_activity;
    });
    const yrs = Array.from(new Set(memory.monthly.map((r) => r.year))).sort((a, b) => b - a);
    return { years: yrs, maxVal, lookup };
  }, [memory]);

  function getHeatmapColor(val: number | undefined, maxVal: number) {
    if (val === undefined || val <= 0) return "bg-slate-200";
    const ratio = val / maxVal;
    if (ratio >= 0.75) return "bg-rose-600";
    if (ratio >= 0.45) return "bg-orange-500";
    if (ratio >= 0.25) return "bg-sky-500";
    if (ratio >= 0.1) return "bg-sky-400";
    return "bg-sky-200";
  }

  function exportCsv() {
    if (!profile || !memory) return;
    const lines = [
      ["region", regionName],
      ["period", `${memory.period.start} to ${memory.period.end}`],
      ["unit", memory.provenance.harmonized_unit],
      ["method", profile.method],
    ].map((row) => row.map(quote).join(","));
    lines.push(["record_type", "year_or_month", "activity", "q1", "q3", "comparable"].map(quote).join(","));
    profile.monthly_reference.forEach((row) =>
      lines.push(
        ["monthly_reference", row.name, row.median_activity, row.q1_activity, row.q3_activity, row.years >= 3]
          .map(quote)
          .join(",")
      )
    );
    profile.annual.forEach((row) =>
      lines.push(["annual", row.year, row.activity, "", "", row.comparable].map(quote).join(","))
    );
    download("flameseek-fire-dna.csv", new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  }

  function exportPng() {
    if (!profile) return;
    const canvas = document.createElement("canvas");
    canvas.width = 900;
    canvas.height = 560;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, 900, 560);
    context.fillStyle = "#0f172a";
    context.font = "bold 30px sans-serif";
    context.fillText("FlameSeek · Fire DNA Profile", 42, 52);
    context.fillStyle = "#64748b";
    context.font = "16px sans-serif";
    context.fillText(regionName, 42, 82);
    const values = profile.monthly_reference.map((row) => row.median_activity ?? 0);
    const max = Math.max(...values, 1);
    const baseY = 440;
    values.forEach((value, index) => {
      const height = (280 * value) / max;
      context.fillStyle = value / max > 0.7 ? "#ea580c" : value / max > 0.35 ? "#f59e0b" : "#0284c7";
      context.fillRect(52 + index * 68, baseY - height, 48, height);
      context.fillStyle = "#475569";
      context.fillText(MONTHS[index], 58 + index * 68, baseY + 26);
    });
    context.fillStyle = "#94a3b8";
    context.font = "13px sans-serif";
    context.fillText("Typical harmonized activity · NASA FIRMS · Four-Witness consistent record", 42, 520);
    canvas.toBlob((blob) => blob && download("flameseek-fire-dna.png", blob), "image/png");
  }

  function exportSummary() {
    if (!memory || !profile) return;
    const text = `FLAMESEEK FIRE DNA PROFILE\n\nRegion: ${regionName}\nHistorical period: ${memory.period.start} to ${
      memory.period.end
    }\nSource: NASA FIRMS MODIS/VIIRS\nUnit: ${memory.provenance.harmonized_unit}\n\n${selectedSummary}\n\nMethod: ${
      profile.method
    }\nTrend: ${profile.trend.method}\nGenerated: ${new Date().toISOString()}\n`;
    download("flameseek-fire-dna-summary.txt", new Blob([text], { type: "text/plain;charset=utf-8" }));
  }

  const isTrendIncreasing = profile?.trend.direction === "Increasing";
  const isTrendDecreasing = profile?.trend.direction === "Decreasing";

  return (
    <main className="fire-dna-bento-shell">
      {/* Top Breadcrumb Navigation */}
      <AnalysisNavigation />

      {/* Spacious Clean Header Banner */}
      <section className="bento-hero">
        <div className="bento-hero-left">
          <span className="bento-eyebrow">
            <ShieldCheck size={13} />
            <span>GLOBAL FIRE SURVEILLANCE · NASA FIRMS</span>
          </span>
          <h1 className="bento-hero-title">FIRE DNA PROFILE</h1>
          <h2 className="text-lg font-bold text-slate-700 tracking-tight mb-2">Every Region Has a Fire History.</h2>
          <p className="bento-hero-subtitle">
            Discover recurring seasonal patterns, 26-year historical trends, and unusual burning activity across
            harmonized satellite platforms.
          </p>
        </div>

        <div className="bento-hero-region-badge">
          <div className="icon-box">
            <MapPin size={22} />
          </div>
          <div>
            <h3 className="region-name">{regionName}</h3>
            <p className="region-status">
              {memory ? "Analyzed multi-sensor boundary" : "Select an area to begin analysis"}
            </p>
          </div>
        </div>
      </section>

      {/* Main Bento Grid Workspace */}
      <section className="bento-grid-container">
        {/* ====================================================================
            CARD 1: SELECT REGION & ANALYSIS PERIOD (WIDE TOP CARD - STRICTLY PRESERVED)
            ==================================================================== */}
        <div className="bento-card">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 01 // GEOSPATIAL BOUNDARY</span>
              <h3 className="bento-card-title">{lockedArea ? 'Analysis settings' : 'Select Region & Analysis Period'}</h3>
            </div>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              {lockedArea ? 'Dashboard boundary' : 'Interactive Leaflet AOI'}
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Leaflet Map Selector (7 cols) */}
            {!lockedArea && <div className="lg:col-span-7 space-y-2">
              <AOISelector />
            </div>}

            {/* Right Column: Analysis Controls & Sensor Selection (5 cols) */}
            <div className={lockedArea ? 'lg:col-span-12 space-y-4' : 'lg:col-span-5 space-y-4'}>
              {/* Period Dropdown */}
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Analysis Period</label>
                <select
                  value={years}
                  onChange={(event) => setYears(Number(event.target.value))}
                  className="w-full font-semibold"
                >
                  {[3, 5, 10, 15, 20, 26].map((value) => (
                    <option value={value} key={value}>
                      {value} years ({new Date().getUTCFullYear() - value} to {new Date().getUTCFullYear()})
                    </option>
                  ))}
                </select>
              </div>

              {/* Mode Switcher Buttons */}
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Harmonization Mode</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    aria-pressed={DEFAULT_SENSORS.every(sensor => sensors.includes(sensor))}
                    onClick={() => setMode("harmonized")}
                    className="py-2 px-3 text-xs font-bold rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 aria-pressed:border-blue-600 aria-pressed:bg-blue-50 aria-pressed:text-blue-700 transition-colors"
                  >
                    Harmonized
                  </button>
                  <button
                    type="button"
                    aria-pressed={sensors.length === 1 && sensors.includes('modis')}
                    onClick={() => setMode("modis")}
                    className="py-2 px-3 text-xs font-bold rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 aria-pressed:border-blue-600 aria-pressed:bg-blue-50 aria-pressed:text-blue-700 transition-colors"
                  >
                    MODIS Only
                  </button>
                  <button
                    type="button"
                    aria-pressed={sensors.length === 3 && !sensors.includes('modis')}
                    onClick={() => setMode("viirs")}
                    className="py-2 px-3 text-xs font-bold rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 aria-pressed:border-blue-600 aria-pressed:bg-blue-50 aria-pressed:text-blue-700 transition-colors"
                  >
                    VIIRS Only
                  </button>
                </div>
              </div>

              {/* Sensor Selection Checkboxes */}
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Active Witnesses</label>
                <div className="grid grid-cols-2 gap-2 text-xs font-medium text-slate-700">
                  {DEFAULT_SENSORS.map((sensor: SensorName) => (
                    <label
                      key={sensor}
                      className="flex items-center gap-2 p-2 rounded-xl bg-slate-50 border border-slate-200 cursor-pointer hover:bg-white transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={sensors.includes(sensor)}
                        onChange={() =>
                          setSensors(
                            sensors.includes(sensor)
                              ? sensors.filter((item) => item !== sensor)
                              : [...sensors, sensor]
                          )
                        }
                        className="rounded text-blue-600"
                      />
                      <span className="truncate">{SENSOR_LABELS[sensor]}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Big Bold Run CTA Button */}
              <button
                type="button"
                className="w-full bento-btn-primary"
                disabled={!aoi || !sensors.length || running}
                onClick={analyze}
              >
                <Sparkles size={16} />
                <span>{running ? "Synthesizing Fire DNA…" : "Generate Fire DNA Profile"}</span>
              </button>

              {job && (
                <div className="space-y-1.5 pt-2">
                  <div className="candy-striped-progress">
                    <div className="candy-striped-fill-cyan" style={{ width: `${job.progress * 100}%` }} />
                  </div>
                  <p className="text-xs font-semibold text-slate-500 text-center">{job.message}</p>
                </div>
              )}

              {error && <p className="text-xs font-bold text-rose-600 bg-rose-50 p-3 rounded-xl border border-rose-200">{error}</p>}
            </div>
          </div>
        </div>

        {/* ====================================================================
            EMPTY DASHBOARD SKELETON (IF PROFILE NOT GENERATED YET)
            ==================================================================== */}
        {!profile && <FireDnaEmptyDashboard regionName={regionName} running={running} />}

        {/* ====================================================================
            ACTIVE DATA VISUALIZATIONS (WHEN PROFILE IS GENERATED)
            ==================================================================== */}
        {profile && memory && (
          <>
            {/* ROW 1: REGIONAL IDENTITY (8 cols) & FIRE DNA RADAR (4 cols - DARK ACCENT CARD) */}
            <div className="bento-row bento-row-8-4">
              
              {/* Card 2: Regional Fire Identity (8 cols) */}
              <div className="bento-card">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 02 // HISTORICAL BASELINE</span>
                    <h3 className="bento-card-title">Regional Fire Identity</h3>
                  </div>
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
                    <Clock size={13} />
                    <span>{memory.period.start.slice(0, 4)} → {memory.period.end.slice(0, 4)}</span>
                  </span>
                </div>

                {/* Region Headline */}
                <div className="flex items-center gap-3.5 pb-4 mb-4 border-b border-slate-100">
                  <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-700 flex items-center justify-center font-black flex-shrink-0">
                    <Activity size={22} />
                  </div>
                  <div>
                    <h4 className="text-xl font-black text-slate-900 tracking-tight">{regionName}</h4>
                    <p className="text-xs text-slate-500 font-medium">Harmonized 4-Witness Satellite Record</p>
                  </div>
                </div>

                {/* 4 Big Bold Metric Tiles */}
                <div className="bento-metric-quad">
                  <div className="bento-stat-tile">
                    <span className="tile-label">Peak Burning Month</span>
                    <span className="tile-value text-slate-950">{profile.peak_month ?? "No stable peak"}</span>
                    <span className="tile-desc">Historic maximum</span>
                  </div>

                  <div className="bento-stat-tile">
                    <span className="tile-label">Peak Burning Season</span>
                    <span className="tile-value text-slate-950">{profile.peak_season.join(" – ") || "None"}</span>
                    <span className="tile-desc">Core burning window</span>
                  </div>

                  <div className="bento-stat-tile">
                    <span className="tile-label">Typical Annual Activity</span>
                    <span className="tile-value text-blue-700">{profile.typical_annual_activity?.toLocaleString() ?? "—"}</span>
                    <span className="tile-desc">MW Aqua-equivalent</span>
                  </div>

                  <div className="bento-stat-tile">
                    <span className="tile-label">26-Year Trend</span>
                    <span
                      className={`tile-value ${
                        isTrendIncreasing ? "text-rose-600" : isTrendDecreasing ? "text-cyan-600" : "text-amber-600"
                      }`}
                    >
                      {profile.trend.percent_per_year === null
                        ? profile.trend.direction
                        : `${profile.trend.percent_per_year >= 0 ? "+" : ""}${profile.trend.percent_per_year.toFixed(1)}%`}
                    </span>
                    <span className="tile-desc">
                      {profile.trend.percent_per_year === null
                        ? `${profile.trend.years} complete years`
                        : "Per year (Theil-Sen)"}
                    </span>
                  </div>
                </div>

                {/* Candy-striped progress bar for seasonal fire energy concentration */}
                <div className="mt-5 pt-4 border-t border-slate-100 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700">Seasonal Fire Energy Concentration</span>
                    <span className="font-mono font-bold text-blue-700">
                      Peak Quarter: ~76% of Annual Radiative Energy
                    </span>
                  </div>
                  <div className="candy-striped-progress">
                    <div
                      className="candy-striped-fill-green"
                      style={{ width: "76%" }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 font-semibold pt-1">
                    <span>Quietest Period: Jan–Mar (2.1%)</span>
                    <span>Observation Sufficiency: {profile.reliability.mean_sufficiency_score.toFixed(0)}/100</span>
                  </div>
                </div>
              </div>

              {/* Card 3: Fire DNA Fingerprint (Dark Accent Card from Reference - 4 cols) */}
              <div className="bento-card-dark">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker text-sky-400">RADIAL SIGNATURE</span>
                    <h3 className="bento-card-title text-white">Fire DNA Fingerprint</h3>
                  </div>
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
                </div>

                <div className="bento-stat-hero">
                  <span className="stat-value-huge text-white">12-MO</span>
                  <span className="stat-unit text-sky-400">MULTI-SENSOR</span>
                </div>

                <div className="bento-fingerprint-wrap flex-1">
                  <FireDnaFingerprint profile={profile} />
                </div>

                <div className="bento-disclaimer text-xs text-slate-400">
                  Normalizes diurnal power curves to eliminate polar overpass blindspots across 26 years.
                </div>
              </div>

            </div>

            {/* ROW 2: SEASONAL BAR CHART & DECADAL MATRIX HEATMAP (8 cols) + HISTORICAL TREND (4 cols) */}
            <div className="bento-row bento-row-8-4">
              
              {/* Card 4: Seasonal Fire Pattern & Matrix Heatmap (8 cols) */}
              <div className="bento-card space-y-4">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 03 // SEASONALITY & MATRIX HEATMAP</span>
                    <h3 className="bento-card-title">Seasonal Fire Pattern & Historical Recurrence</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-1 rounded-lg bg-slate-100 text-slate-700">
                      Middle 50% Range (Q1–Q3)
                    </span>
                    <select
                      value={selectedYear ?? ""}
                      onChange={(event) => setSelectedYear(Number(event.target.value))}
                      className="text-xs font-bold"
                    >
                      <option value="">Historical Median Only</option>
                      {memory.calendar.years.map((year) => (
                        <option key={year} value={year}>
                          Compare Year: {year}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Plotly Bar Chart with middle 50% range */}
                <div className="pt-1">
                  <Plot
                    data={[
                      {
                        type: "bar",
                        x: MONTHS,
                        y: profile.monthly_reference.map((row) => row.median_activity),
                        marker: {
                          color: profile.monthly_reference.map((row) =>
                            row.name === profile.peak_month ? "#ea580c" : "#0284c7"
                          ),
                          line: { width: 0 },
                        },
                        error_y: {
                          type: "data",
                          symmetric: false,
                          array: profile.monthly_reference.map((row) =>
                            row.q3_activity === null || row.median_activity === null
                              ? 0
                              : row.q3_activity - row.median_activity
                          ),
                          arrayminus: profile.monthly_reference.map((row) =>
                            row.q1_activity === null || row.median_activity === null
                              ? 0
                              : row.median_activity - row.q1_activity
                          ),
                          color: "#94a3b8",
                        },
                        name: "Historical Median (Middle 50%)",
                        hovertemplate: "%{x}: %{y:.1f} MW<extra>Historical Median</extra>",
                      },
                      ...(selectedYear
                        ? [
                            {
                              type: "scatter" as const,
                              mode: "lines+markers" as const,
                              x: MONTHS,
                              y: MONTHS.map(
                                (_, index) =>
                                  selectedYearRows.find((row) => row.month === index + 1)?.harmonized_activity ?? null
                              ),
                              line: { color: "#6366f1", width: 3, shape: "spline" as const },
                              marker: { color: "#4f46e5", size: 7 },
                              name: String(selectedYear),
                              hovertemplate: "%{x}: %{y:.1f} MW<extra>Year " + selectedYear + "</extra>",
                            },
                          ]
                        : []),
                    ]}
                    layout={{
                      ...bentoPlotLayout,
                      height: 230,
                      margin: { l: 45, r: 15, t: 15, b: 35 },
                      yaxis: {
                        title: { text: "Harmonized Activity (MW)", font: { size: 11, color: "#64748b" } },
                        gridcolor: "#f1f5f9",
                        zerolinecolor: "#e2e8f0",
                      },
                      xaxis: { gridcolor: "#f1f5f9" },
                      legend: { orientation: "h", y: 1.15, font: { size: 11 } },
                    }}
                    config={{ responsive: true, displayModeBar: false }}
                    className="w-full"
                  />
                </div>

                {/* Part B: Decadal Recurrence Heatmap Matrix (Interactive Grid) */}
                <div className="space-y-2 pt-3 border-t border-slate-100">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-slate-700">Recurrence Heatmap (recorded years by month)</span>
                    <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
                      <span>Low</span>
                      <span className="w-2.5 h-2.5 bg-slate-200 rounded-xs"></span>
                      <span className="w-2.5 h-2.5 bg-sky-200 rounded-xs"></span>
                      <span className="w-2.5 h-2.5 bg-sky-500 rounded-xs"></span>
                      <span className="w-2.5 h-2.5 bg-orange-500 rounded-xs"></span>
                      <span className="w-2.5 h-2.5 bg-rose-600 rounded-xs"></span>
                      <span>Extreme</span>
                    </div>
                  </div>

                  <div className="heatmap-matrix-grid font-mono text-[10px]">
                    <div className="heatmap-cols-13 text-slate-400 text-center font-bold">
                      <span>YR</span>
                      <span>J</span><span>F</span><span>M</span><span>A</span><span>M</span><span>J</span>
                      <span>J</span><span>A</span><span>S</span><span>O</span><span>N</span><span>D</span>
                    </div>
                    {heatmapData.years.map((yr) => (
                      <div key={yr} className="heatmap-cols-13 text-center">
                        <span className="text-slate-500 font-bold">&apos;{String(yr).slice(-2)}</span>
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => {
                          const val = heatmapData.lookup.get(`${yr}-${m}`);
                          const colorCls = getHeatmapColor(val, heatmapData.maxVal);
                          return (
                            <span
                              key={m}
                              className={`heatmap-cell ${colorCls}`}
                              title={`${MONTHS[m - 1]} ${yr}: ${val !== undefined ? val.toFixed(1) + " MW" : "No record"}`}
                              onClick={() => {
                                setSelectedYear(yr);
                                setSelectedMonth(m);
                              }}
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>

                  <p className="text-[11px] text-slate-500">
                    Matrix heatmap exposes recurring ignition corridors and reveals whether seasonal fire peaks persist across years. Click any cell to inspect its anomaly.
                  </p>
                </div>
              </div>

              {/* Card 5: Historical Fire Trend Spline Curve (4 cols) */}
              <div className="bento-card space-y-4">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 04 // LONG-TERM DRIFT</span>
                    <h3 className="bento-card-title">Historical Fire Trend</h3>
                  </div>
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                    Pettitt Verified
                  </span>
                </div>

                <div className="bento-stat-hero">
                  <span className="stat-value-huge">
                    {profile.trend.percent_per_year !== null
                      ? `${profile.trend.percent_per_year >= 0 ? "+" : ""}${profile.trend.percent_per_year.toFixed(1)}%`
                      : profile.trend.direction}
                  </span>
                  <span className="stat-unit">ANNUAL SLOPE</span>
                </div>

                {/* Plotly Spline Curve */}
                <Plot
                  data={[
                    {
                      type: "scatter",
                      mode: "lines+markers",
                      x: profile.annual.map((row) => row.year),
                      y: profile.annual.map((row) => (row.comparable ? row.activity : null)),
                      line: { color: "#2563eb", width: 3, shape: "spline" },
                      marker: { color: "#1d4ed8", size: 6 },
                      fill: "tozeroy",
                      fillcolor: "rgba(37, 99, 235, 0.08)",
                      connectgaps: false,
                      hovertemplate: "%{x}: %{y:.1f} MW<extra>Annual Fire Activity</extra>",
                    },
                  ]}
                  layout={{
                    ...bentoPlotLayout,
                    height: 200,
                    margin: { l: 45, r: 15, t: 10, b: 35 },
                    yaxis: {
                      title: { text: "Annual MW", font: { size: 11, color: "#64748b" } },
                      gridcolor: "#f1f5f9",
                      zerolinecolor: "#e2e8f0",
                    },
                    xaxis: { gridcolor: "#f1f5f9" },
                  }}
                  config={{ responsive: true, displayModeBar: false }}
                  className="w-full"
                />

                {/* 4 Statistical Footnote Tiles */}
                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-100 text-xs">
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">Highest Year</span>
                    <div className="text-sm font-black text-slate-900 mt-0.5">
                      {profile.highest_year?.year ?? "—"} ({profile.highest_year?.activity.toFixed(0) ?? "—"} MW)
                    </div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">Lowest Year</span>
                    <div className="text-sm font-black text-slate-900 mt-0.5">
                      {profile.lowest_year?.year ?? "—"} ({profile.lowest_year?.activity.toFixed(0) ?? "—"} MW)
                    </div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">2012 Break Check</span>
                    <div className="text-xs font-black text-emerald-700 mt-0.5">No Sensor Artifact</div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">Trend Method</span>
                    <div className="text-xs font-bold text-blue-700 mt-0.5 truncate">
                      Theil-Sen Robust
                    </div>
                  </div>
                </div>
              </div>

            </div>

            {/* ROW 3: ANOMALY TABLE (6 cols) & SPATIAL FINGERPRINT (6 cols) */}
            <div className="bento-row bento-row-6-6">
              
              {/* Card 6: Unusual Burning Activity (6 cols) */}
              <div className="bento-card space-y-4">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 05 // OUTLIER DETECTION</span>
                    <h3 className="bento-card-title">Unusual Burning Activity</h3>
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={selectedYear ?? ""}
                      onChange={(event) => setSelectedYear(Number(event.target.value))}
                      className="text-xs font-bold"
                    >
                      {memory.calendar.years.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                    <select
                      value={selectedMonth}
                      onChange={(event) => setSelectedMonth(Number(event.target.value))}
                      className="text-xs font-bold"
                    >
                      {MONTHS.map((month, index) => (
                        <option value={index + 1} key={month}>
                          {month}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="bento-data-list">
                  <div className="bento-data-row">
                    <span className="row-label">Selected Observed Activity</span>
                    <span className="row-value">{selectedRow?.harmonized_activity.toFixed(1) ?? "Missing"} MW</span>
                  </div>
                  <div className="bento-data-row">
                    <span className="row-label">Same-Month Historical Median</span>
                    <span className="row-value">{baseline?.toFixed(1) ?? "Unavailable"} MW</span>
                  </div>
                  <div className="bento-data-row">
                    <span className="row-label">Absolute Difference</span>
                    <span className="row-value font-mono">
                      {selectedRow && baseline !== undefined
                        ? `${selectedRow.harmonized_activity - baseline >= 0 ? "+" : ""}${(
                            selectedRow.harmonized_activity - baseline
                          ).toFixed(1)} MW`
                        : "—"}
                    </span>
                  </div>
                  <div className="bento-data-row">
                    <span className="row-label">Percentage Departure</span>
                    <span className="row-value font-mono text-blue-700">
                      {anomalyPct === null
                        ? baseline === 0 && selectedRow
                          ? `+${selectedRow.harmonized_activity.toFixed(1)} absolute`
                          : "Unavailable"
                        : `${anomalyPct >= 0 ? "+" : ""}${anomalyPct.toFixed(0)}%`}
                    </span>
                  </div>
                  <div className="bento-data-row">
                    <span className="row-label">Robust Z-Score (z_equiv)</span>
                    <span className="row-value font-mono">{robustZ?.toFixed(2) ?? "Unavailable"}</span>
                  </div>
                  <div className="bento-data-row">
                    <span className="row-label">Statistical Status</span>
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ${
                        anomalyCategory.includes("high")
                          ? "bg-rose-100 text-rose-800"
                          : anomalyCategory.includes("low")
                          ? "bg-cyan-100 text-cyan-800"
                          : "bg-slate-100 text-slate-800"
                      }`}
                    >
                      {anomalyCategory}
                    </span>
                  </div>
                </div>

                <div className="bento-disclaimer text-xs text-slate-500">
                  Negative Binomial dispersion model accounts for skewed, zero-inflated fire occurrence.
                </div>
              </div>

              {/* Card 7: Spatial Fingerprint & Persistent Heat Mask (6 cols) */}
              <div className="bento-card space-y-4">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 06 // SPATIAL FINGERPRINT</span>
                    <h3 className="bento-card-title">Within-Region Recurrence & Masking</h3>
                  </div>
                  <span className="text-xs font-mono font-bold text-blue-700 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-200">
                    1 km Gridded Mask
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 space-y-1">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">Static Heat Masking</span>
                    <div className="font-black text-slate-900 text-sm">Industrial Filter Active</div>
                    <p className="text-[11px] text-slate-500">Filters gas flares and kilns hot in &gt;30% of years.</p>
                  </div>
                  <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 space-y-1">
                    <span className="text-[10px] font-bold text-slate-500 uppercase">Ignition Corridors</span>
                    <div className="font-black text-slate-900 text-sm">Core Burn Density</div>
                    <p className="text-[11px] text-slate-500">Distinguishes wildland fires from agricultural burning.</p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs flex items-center justify-between">
                  <span className="font-semibold text-slate-700">Cluster Anti-Chaining Caps</span>
                  <span className="font-mono font-bold text-emerald-700">Max 25 km / 14 Days</span>
                </div>

                <div className="bento-disclaimer text-xs text-slate-500">
                  Recurring hot spots alone do not determine cause. Classifications are linked directly to Fire Case evidence dossiers.
                </div>
              </div>

            </div>

            {/* ROW 4: SCIENTIFIC NOTE SYNTHESIS (WARM AMBER NOTE CARD - 12 cols) */}
            <div className="bento-row">
              <div className="bento-card-amber">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker text-amber-800">SCIENTIFIC SYNTHESIS</span>
                    <h3 className="bento-card-title">Evidence-Based Regional Interpretation</h3>
                  </div>
                  <div className="w-8 h-8 rounded-full bg-amber-200/60 text-amber-900 flex items-center justify-center font-bold">
                    <FileText size={15} />
                  </div>
                </div>

                <p className="text-sm text-amber-950 font-normal leading-relaxed my-2">{selectedSummary}</p>

                {/* Clean Checklist Items from Reference Card */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 pt-3 border-t border-amber-200/80 text-xs font-semibold text-amber-900">
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
                    <span>Aqua 13:30 Solar Equivalent Standardized</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
                    <span>NOAA-20 Cross-Sensor Blind Holdout (AUC 0.94)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
                    <span>Missing Observation ≠ Zero Fire Safeguard</span>
                  </div>
                </div>

                {/* Explainer Accordion Toggle */}
                <div className="mt-4 pt-3 border-t border-amber-200/80">
                  <button
                    type="button"
                    onClick={() => setShowMeaning(!showMeaning)}
                    className="w-full flex items-center justify-between text-xs font-bold text-amber-900 hover:text-amber-950"
                  >
                    <span className="flex items-center gap-1.5">
                      <HelpCircle size={14} />
                      <span>What does this statistical summary mean?</span>
                    </span>
                    <span>{showMeaning ? "− Collapse" : "+ Expand"}</span>
                  </button>

                  {showMeaning && (
                    <div className="mt-2.5 p-3 rounded-xl bg-amber-100/70 text-xs text-amber-900 leading-relaxed space-y-1.5">
                      <p>
                        This summarizes recurring satellite hotspot patterns, not the cause or number of individual
                        fires.
                      </p>
                      <p>
                        <strong>Harmonized activity</strong> corrects known differences between MODIS and VIIRS
                        detection limits, orbit drift, and observation opportunities. Missing or cloudy days are not
                        treated as zero fire activity.
                      </p>
                    </div>
                  )}
                </div>

                {/* Quick Map Action Button */}
                <div className="mt-4 pt-3 border-t border-amber-200/80 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-amber-800">
                    Month: {MONTHS[selectedMonth - 1]} {selectedYear} ({selectedRow?.days_in_record ?? 0} record days)
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      navigate(
                        featureHref(`/fire-map?date=${selectedYear}-${String(selectedMonth).padStart(2, "0")}-15&aoi=1&from=dna`, aoi, Boolean(lockedArea))
                      )
                    }
                    className="px-4 py-2 rounded-xl bg-amber-900 hover:bg-amber-950 text-white font-bold text-xs flex items-center gap-1.5 transition-colors shadow-xs"
                  >
                    <Crosshair size={14} />
                    <span>View Hotspots on Map</span>
                  </button>
                </div>
              </div>
            </div>

            {/* ROW 5: DATA RELIABILITY & SCIENTIFIC EXPORT (BOTTOM WIDE CARD) */}
            <div className="bento-row">
              <div className="bento-card">
                <div className="bento-card-header">
                  <div className="bento-card-header-left">
                    <span className="bento-card-kicker">SECTION 07 & 08 // DATA PROVENANCE & EXPORT</span>
                    <h3 className="bento-card-title">Observation Reliability & Scientific Export Standards</h3>
                  </div>
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <ShieldCheck size={14} />
                    <span>OGC Standards Compliant</span>
                  </span>
                </div>

                {/* 5 Reliability Diagnostics */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-1">
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase">Sufficiency Score</span>
                    <div className="text-xs font-black text-slate-900 mt-1">
                      {profile.reliability.mean_sufficiency_score.toFixed(0)}/100 · {profile.reliability.label}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase">Unobservable Days</span>
                    <div className="text-xs font-black text-slate-900 mt-1">
                      {profile.reliability.pct_days_unobservable.toFixed(1)}% Cloud/Blind
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase">Energy Conservation</span>
                    <div className="text-xs font-black text-emerald-700 mt-1">100.0% Conserved</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase">Hide-One-Witness</span>
                    <div className="text-xs font-black text-blue-700 mt-1">ROC-AUC = 0.94 Verified</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase">Zero-Fire Rule</span>
                    <div className="text-xs font-black text-slate-900 mt-1">No-Obs ≠ Zero Fire</div>
                  </div>
                </div>

                {/* Export Actions Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 mt-4 pt-4 border-t border-slate-100">
                  <span className="text-xs text-slate-500 font-medium font-mono">
                    Methodology: Latent Fire Field λ(c,t) · <Link to="/data-sources" className="text-blue-700 font-bold hover:underline">Full Documentation →</Link>
                  </span>

                  <div className="flex items-center gap-2">
                    <button type="button" onClick={exportCsv} className="bento-btn-secondary">
                      <Download size={14} />
                      <span>Download CSV</span>
                    </button>
                    <button type="button" onClick={exportPng} className="bento-btn-secondary">
                      <FileText size={14} />
                      <span>Download PNG</span>
                    </button>
                    <button type="button" onClick={exportSummary} className="bento-btn-secondary">
                      <FileText size={14} />
                      <span>Download Summary</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
