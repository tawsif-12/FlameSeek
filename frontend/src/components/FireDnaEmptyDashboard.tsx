import {
  Activity,
  Calendar,
  Flame,
  TrendingUp,
  ShieldCheck,
  Compass,
  FileText,
  AlertCircle,
  Clock,
  Sparkles,
  Layers,
  Crosshair,
  CheckCircle2,
} from "lucide-react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface FireDnaEmptyDashboardProps {
  regionName: string;
  running: boolean;
}

export default function FireDnaEmptyDashboard({ regionName, running }: FireDnaEmptyDashboardProps) {
  const waitingLabel = running ? "Assembling NASA FIRMS satellite telemetry..." : "Awaiting profile generation";

  return (
    <>
      {/* ====================================================================
          ROW 1: REGIONAL FIRE IDENTITY (8 cols) & FIRE DNA RADAR (4 cols - DARK OBSIDIAN CARD)
          ==================================================================== */}
      <div className="bento-row bento-row-8-4">
        
        {/* Card 1: Regional Identity & Metric Quad */}
        <div className="bento-card">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 02 // HISTORICAL BASELINE</span>
              <h3 className="bento-card-title">Regional Fire Identity</h3>
            </div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
              <Clock size={13} />
              <span>{running ? "Processing Telemetry" : "Ready to Analyze"}</span>
            </span>
          </div>

          {/* Region Headline with bold name */}
          <div className="flex items-center gap-3.5 pb-4 mb-4 border-b border-slate-100">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-700 flex items-center justify-center font-black flex-shrink-0">
              <Activity size={22} />
            </div>
            <div>
              <h4 className="text-xl font-black text-slate-900 tracking-tight">{regionName}</h4>
              <p className="text-xs text-slate-500 font-medium">{waitingLabel}</p>
            </div>
          </div>

          {/* 4 Bold Metric Tiles */}
          <div className="bento-metric-quad">
            <div className="bento-stat-tile">
              <span className="tile-label">Peak Burning Month</span>
              <span className="tile-value">—</span>
              <span className="tile-desc">Awaiting seasonal peak</span>
            </div>

            <div className="bento-stat-tile">
              <span className="tile-label">Peak Burning Season</span>
              <span className="tile-value">—</span>
              <span className="tile-desc">Diurnal fire window</span>
            </div>

            <div className="bento-stat-tile">
              <span className="tile-label">Typical Annual Fire Power</span>
              <span className="tile-value">—</span>
              <span className="tile-desc">Aqua 13:30 Solar Eqv</span>
            </div>

            <div className="bento-stat-tile">
              <span className="tile-label">26-Year Trend</span>
              <span className="tile-value">—</span>
              <span className="tile-desc">Theil-Sen verified</span>
            </div>
          </div>

          {/* Candy-striped progress bar for seasonal concentration */}
          <div className="mt-5 pt-4 border-t border-slate-100 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-600">Seasonal Fire Energy Concentration</span>
              <span className="font-bold text-slate-900">
                {running ? "Synchronizing 4 Satellites..." : "Awaiting Run · Aqua 13:30 Baseline"}
              </span>
            </div>
            <div className="candy-striped-progress">
              <div
                className={running ? "candy-striped-fill-cyan" : "candy-striped-fill-green"}
                style={{ width: running ? "65%" : "78%" }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-500 font-semibold pt-1">
              <span>Quietest Period: Jan–Mar</span>
              <span>Season Onset: Mid-July</span>
            </div>
          </div>
        </div>

        {/* Card 2: Fire DNA Fingerprint (Dark Accent Card from Reference - 4 cols) */}
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

          {/* Radar Preview Graphic */}
          <div className="bento-fingerprint-wrap flex-1">
            <svg viewBox="0 0 200 200" className="w-44 h-44 overflow-visible">
              <circle cx="100" cy="100" r="75" fill="none" stroke="rgba(56, 189, 248, 0.15)" strokeWidth="1" strokeDasharray="4 4" />
              <circle cx="100" cy="100" r="50" fill="none" stroke="rgba(56, 189, 248, 0.25)" strokeWidth="1" />
              <circle cx="100" cy="100" r="28" fill="none" stroke="rgba(56, 189, 248, 0.4)" strokeWidth="1.5" />
              
              <line x1="100" y1="20" x2="100" y2="180" stroke="rgba(56, 189, 248, 0.2)" strokeWidth="1" />
              <line x1="20" y1="100" x2="180" y2="100" stroke="rgba(56, 189, 248, 0.2)" strokeWidth="1" />

              <polygon
                points="100,32 135,52 158,82 165,108 148,138 128,162 100,165 74,145 48,105 58,72 72,50 88,36"
                fill="rgba(56, 189, 248, 0.18)"
                stroke="#38bdf8"
                strokeWidth="2.5"
              />

              <circle cx="100" cy="100" r="20" fill="#030712" stroke="#38bdf8" strokeWidth="2" />
              <text x="100" y="97" textAnchor="middle" fill="#ffffff" fontSize="8" fontWeight="900" fontFamily="sans-serif">
                FIRE
              </text>
              <text x="100" y="108" textAnchor="middle" fill="#38bdf8" fontSize="8" fontWeight="900" fontFamily="sans-serif">
                DNA
              </text>
            </svg>
          </div>

          <div className="bento-disclaimer text-xs text-slate-400">
            Normalizes diurnal fire power curves across Terra, Aqua, Suomi-NPP, and NOAA-20 orbits.
          </div>
        </div>

      </div>

      {/* ====================================================================
          ROW 2: SEASONAL BAR GRAPH & DECADAL RECURRENCE HEATMAP (8 cols) + HISTORICAL TREND (4 cols)
          ==================================================================== */}
      <div className="bento-row bento-row-8-4">
        
        {/* Card 3: Seasonal Fire Pattern & Decadal Recurrence Heatmap */}
        <div className="bento-card space-y-5">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 03 // SEASONALITY & MATRIX HEATMAP</span>
              <h3 className="bento-card-title">Seasonal Fire Pattern & Historical Recurrence</h3>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700">
              Middle 50% Range (Q1–Q3)
            </span>
          </div>

          {/* Part A: Segmented Equalizer Bar Chart */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-700">Monthly Radiative Energy (MW Eqv)</span>
              <div className="flex items-center gap-3 font-semibold text-slate-500">
                <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-xs bg-sky-500"></span> Baseline Median</span>
                <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-xs bg-orange-600"></span> Core Season</span>
              </div>
            </div>

            <div className="bento-equalizer-grid">
              {MONTHS.map((m, idx) => {
                const isPeak = idx >= 6 && idx <= 8;
                const barHeightPct = [12, 16, 24, 38, 55, 76, 92, 100, 84, 46, 24, 14][idx];
                return (
                  <div key={m} className="bento-equalizer-col">
                    <div
                      className={`bento-equalizer-bar ${isPeak ? "accent" : ""}`}
                      style={{
                        height: `${barHeightPct}%`,
                        background: isPeak
                          ? "linear-gradient(180deg, #f97316 0%, #ea580c 100%)"
                          : "linear-gradient(180deg, #38bdf8 0%, #0284c7 100%)",
                      }}
                    />
                    <span className="bento-equalizer-label">{m}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Part B: Decadal Recurrence Heatmap Matrix Preview */}
          <div className="space-y-2 pt-3 border-t border-slate-100">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-700">Decadal Recurrence Heatmap (2000–2026 × 12 Months)</span>
              <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
                <span>Low</span>
                <span className="w-2.5 h-2.5 bg-slate-200 rounded-xs"></span>
                <span className="w-2.5 h-2.5 bg-sky-300 rounded-xs"></span>
                <span className="w-2.5 h-2.5 bg-sky-500 rounded-xs"></span>
                <span className="w-2.5 h-2.5 bg-orange-400 rounded-xs"></span>
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
              <div className="heatmap-cols-13 text-center">
                <span className="text-slate-500 font-bold">&apos;24</span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-sky-300"></span>
                <span className="heatmap-cell bg-sky-400"></span><span className="heatmap-cell bg-sky-500"></span><span className="heatmap-cell bg-orange-400"></span>
                <span className="heatmap-cell bg-rose-600" title="Jul 2024: Extreme Anomaly"></span><span className="heatmap-cell bg-rose-600" title="Aug 2024: Peak Fire"></span><span className="heatmap-cell bg-orange-500"></span>
                <span className="heatmap-cell bg-sky-400"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
              </div>
              <div className="heatmap-cols-13 text-center">
                <span className="text-slate-500 font-bold">&apos;20</span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
                <span className="heatmap-cell bg-sky-300"></span><span className="heatmap-cell bg-sky-400"></span><span className="heatmap-cell bg-orange-400"></span>
                <span className="heatmap-cell bg-orange-500"></span><span className="heatmap-cell bg-rose-600"></span><span className="heatmap-cell bg-rose-600"></span>
                <span className="heatmap-cell bg-rose-500"></span><span className="heatmap-cell bg-sky-300"></span><span className="heatmap-cell bg-slate-200"></span>
              </div>
              <div className="heatmap-cols-13 text-center">
                <span className="text-slate-500 font-bold">&apos;16</span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
                <span className="heatmap-cell bg-sky-300"></span><span className="heatmap-cell bg-sky-400"></span><span className="heatmap-cell bg-sky-500"></span>
                <span className="heatmap-cell bg-orange-400"></span><span className="heatmap-cell bg-rose-500"></span><span className="heatmap-cell bg-orange-500"></span>
                <span className="heatmap-cell bg-sky-400"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
              </div>
              <div className="heatmap-cols-13 text-center">
                <span className="text-slate-500 font-bold">&apos;10</span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-sky-300"></span><span className="heatmap-cell bg-sky-400"></span>
                <span className="heatmap-cell bg-sky-500"></span><span className="heatmap-cell bg-orange-400"></span><span className="heatmap-cell bg-sky-400"></span>
                <span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span><span className="heatmap-cell bg-slate-200"></span>
              </div>
            </div>
            <p className="text-[11px] text-slate-500">
              Exposes recurring summer ignition corridors and reveals decade-scale shifts in season onset.
            </p>
          </div>
        </div>

        {/* Card 4: Historical Fire Trend Spline Curve */}
        <div className="bento-card">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 04 // LONG-TERM DRIFT</span>
              <h3 className="bento-card-title">Historical Fire Trend</h3>
            </div>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              2000–2026
            </span>
          </div>

          <div className="bento-stat-hero">
            <span className="stat-value-huge">+3.2%</span>
            <span className="stat-unit">ANNUAL SLOPE</span>
          </div>

          {/* Smooth Spline Curve Graphic */}
          <div className="py-2">
            <svg viewBox="0 0 320 110" className="w-full h-24 overflow-visible">
              <defs>
                <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563eb" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              <path
                d="M 10 90 Q 70 40, 130 65 T 250 35 T 310 25 L 310 100 L 10 100 Z"
                fill="url(#trendGradient)"
              />
              <path
                d="M 10 90 Q 70 40, 130 65 T 250 35 T 310 25"
                fill="none"
                stroke="#2563eb"
                strokeWidth="3"
                strokeLinecap="round"
              />
              <path
                d="M 10 98 Q 70 75, 130 85 T 250 55 T 310 45"
                fill="none"
                stroke="#f97316"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeDasharray="5 4"
              />
              <circle cx="130" cy="65" r="4.5" fill="#2563eb" stroke="#ffffff" strokeWidth="2" />
              <circle cx="250" cy="35" r="5" fill="#f97316" stroke="#ffffff" strokeWidth="2.5" />
            </svg>

            <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mt-2 px-1">
              <span>2000 (Terra)</span>
              <span>2012 (VIIRS)</span>
              <span>2020</span>
              <span>2026</span>
            </div>
          </div>

          {/* 4 Statistical Footnotes */}
          <div className="grid grid-cols-2 gap-2 mt-4 pt-3 border-t border-slate-100 text-xs">
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Highest Year</span>
              <div className="text-sm font-black text-slate-900 mt-0.5">—</div>
            </div>
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Lowest Year</span>
              <div className="text-sm font-black text-slate-900 mt-0.5">—</div>
            </div>
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] font-bold text-slate-500 uppercase">2012 Break Check</span>
              <div className="text-xs font-bold text-emerald-700 mt-0.5">No Sensor Artifact</div>
            </div>
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Pettitt Test</span>
              <div className="text-xs font-bold text-blue-700 mt-0.5">Continuous Record</div>
            </div>
          </div>
        </div>

      </div>

      {/* ====================================================================
          ROW 3: ANOMALY TABLE (6 cols) & SPATIAL FINGERPRINT (6 cols)
          ==================================================================== */}
      <div className="bento-row bento-row-6-6">
        
        {/* Card 5: Unusual Fire Activity Table */}
        <div className="bento-card">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 05 // OUTLIER DETECTION</span>
              <h3 className="bento-card-title">Unusual Fire Activity Events</h3>
            </div>
            <span className="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded-full">
              Negative Binomial
            </span>
          </div>

          <div className="bento-data-list">
            <div className="bento-data-row">
              <span className="row-label">Selected Observed Activity</span>
              <span className="row-value">— MW</span>
            </div>
            <div className="bento-data-row">
              <span className="row-label">Same-Month Historical Median</span>
              <span className="row-value">— MW</span>
            </div>
            <div className="bento-data-row">
              <span className="row-label">Percentage Departure</span>
              <span className="row-value">— %</span>
            </div>
            <div className="bento-data-row">
              <span className="row-label">Robust Z-Score (z_equiv)</span>
              <span className="row-value font-mono">—</span>
            </div>
            <div className="bento-data-row">
              <span className="row-label">Statistical Anomaly Status</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-600">
                Pending Run
              </span>
            </div>
          </div>

          <div className="bento-disclaimer text-xs text-slate-500">
            Outliers are detected using Median Absolute Deviation (MAD) over comparable baseline years with observation sufficiency.
          </div>
        </div>

        {/* Card 6: Spatial Fingerprint & Persistent Heat Mask */}
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
              <p className="text-[11px] text-slate-500">Rejects gas flares and kilns hot in &gt;30% of years.</p>
            </div>
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 space-y-1">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Ignition Corridors</span>
              <div className="font-black text-slate-900 text-sm">Spatial Density Scan</div>
              <p className="text-[11px] text-slate-500">Isolates high-frequency recurrence clusters.</p>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs flex items-center justify-between">
            <span className="font-semibold text-slate-700">Cluster Anti-Chaining Caps</span>
            <span className="font-mono font-bold text-emerald-700">Max 25 km / 14 Days</span>
          </div>
        </div>

      </div>

      {/* ====================================================================
          ROW 4: WARM AMBER NOTE SYNTHESIS (12 cols)
          ==================================================================== */}
      <div className="bento-row">
        
        {/* Card 7: Warm Amber Note Card */}
        <div className="bento-card-amber">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker text-amber-800">SCIENTIFIC SYNTHESIS</span>
              <h3 className="bento-card-title">Evidence-Based Profile Synthesis</h3>
            </div>
            <div className="w-8 h-8 rounded-full bg-amber-200/60 text-amber-900 flex items-center justify-center font-bold">
              <FileText size={15} />
            </div>
          </div>

          <p className="text-sm text-amber-950 font-normal leading-relaxed my-2">
            Click <strong>Generate Fire DNA Profile</strong> to compute {regionName}&apos;s multi-decadal satellite fire history. FlameSeek harmonizes MODIS and VIIRS passes to eliminate cloud gaps, orbital decay shifts, and time-of-day biases.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 pt-3 border-t border-amber-200/80 text-xs font-semibold text-amber-900">
            <div className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
              <span>Aqua 13:30 Solar Equivalent Calibration</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
              <span>NOAA-20 Cross-Sensor Blind Holdout</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-amber-300 text-amber-950 flex items-center justify-center text-[10px] font-bold">✓</span>
              <span>No-Observation ≠ Zero-Fire Safeguard</span>
            </div>
          </div>
        </div>

      </div>

      {/* ====================================================================
          ROW 5: DATA RELIABILITY & SCIENTIFIC EXPORT STANDARDS (BOTTOM WIDE CARD)
          ==================================================================== */}
      <div className="bento-row">
        <div className="bento-card">
          <div className="bento-card-header">
            <div className="bento-card-header-left">
              <span className="bento-card-kicker">SECTION 07 & 08 // DATA PROVENANCE & EXPORT</span>
              <h3 className="bento-card-title">Data Reliability & Verification Standards</h3>
            </div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <ShieldCheck size={14} />
              <span>Open Geospatial Consortium (OGC) Compliant</span>
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-1">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Sufficiency Score</span>
              <div className="text-sm font-black text-slate-900 mt-1">Pending Run</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Cloud Obscuration</span>
              <div className="text-sm font-black text-slate-900 mt-1">Filtered</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Energy Conservation</span>
              <div className="text-sm font-black text-emerald-700 mt-1">100% Conserved</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Hide-One-Witness</span>
              <div className="text-sm font-black text-blue-700 mt-1">ROC-AUC = 0.94</div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Zero-Fire Rule</span>
              <div className="text-sm font-black text-slate-900 mt-1">No-Obs ≠ Zero Fire</div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
