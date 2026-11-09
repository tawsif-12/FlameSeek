import { useState } from "react";
import LazyPlot from "../components/LazyPlot";
import { CalibrationData, CalibrationRow, computed, DriftData, EnergyData, GeoData, Labelled, SiteData, useSiteData } from "../api/harmonized";
import { useLanguage } from "../context/LanguageContext";
import HarmonizedProvenance, { StatusPill } from "../components/HarmonizedProvenance";
import "../harmonized.css";

type PlotProps = React.ComponentProps<typeof LazyPlot>;
type Data = PlotProps["data"][number];
type Layout = NonNullable<PlotProps["layout"]>;

const S1 = "#3987e5"; // validated dark-surface pair (harmonized.css)
const S2 = "#d95926";

const STEPS: [string, string, string][] = [
  ["Read and check every detection", "NASA FIRMS files from MODIS (Terra, Aqua) and VIIRS (S-NPP, NOAA-20, NOAA-21) are read and sanity-checked; low-confidence detections are set aside, not deleted.",
    "Each row keeps its source file and row (stable id). Confidence is mapped to one probability scale per sensor; rows below the nominal class go to a separate table."],
  ["True ground footprints", "A satellite pixel covers a patch of ground that grows toward the swath edge, so each detection is drawn as that patch.",
    "Footprint = rotated rectangle scan_km × track_km centred on the pixel, oriented along the satellite track; area stored in km²."],
  ["Group detections into fire events", "Detections whose footprints touch on the same local solar day, or on consecutive days, form one event; very long or large chains are split.",
    "Graph of footprint overlaps (plus half-diagonal distance) per local solar day, linked across days; connected components = events; extent and duration caps split chains."],
  ["Common grid without double counting", "Fire power is shared over fixed grid cells by footprint area; the total before and after is checked to be identical.",
    "FRP_cell = Σ_i w_ic · FRP_i with Σ_c w_ic = 1. Energy conservation: |Σ FRP_grid − Σ FRP_det| / Σ FRP_det < tolerance."],
  ["Make the sensors comparable", "Where MODIS and VIIRS see the same fire at almost the same time, we fit how their measured power relates.",
    "log10 FRP_VIIRS = a + b · log10 FRP_Aqua; Deming regression with a stated error ratio, near-simultaneous pairs, truncation filter, bootstrap intervals, OLS/ODR bounds on b (config: calibration)."],
  ["Account for fires a sensor cannot see", "Small fires are often missed; we estimate the chance a fire of a given power is detected and how often each place was observed.",
    "P(detect) = logistic(b0 + b1·log10 F − b2·log10 A); observation opportunities O_s from orbits; latent rate λ = N_observed / Σ_overpasses π_s."],
];

const BASE_LAYOUT = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#c6dcf6", family: "Space Grotesk, Inter, sans-serif", size: 12 },
  margin: { t: 28, r: 60, b: 40, l: 230 },
  autosize: true,
  showlegend: false,
  xaxis: { gridcolor: "rgba(148,197,255,0.12)", zeroline: false, color: "#94a3b8" },
  yaxis: { gridcolor: "rgba(0,0,0,0)", color: "#e6f1ff", automargin: true },
  hoverlabel: { bgcolor: "#0a1220", bordercolor: "#6ad7ff", font: { color: "#e6f1ff" } },
};
const CONFIG = { displayModeBar: false, responsive: true };
const hhmm = (h: number) => `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;

function TableToggle({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 6 }}>
      <button className="hz-link-btn" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide table" : "Show as table"}</button>
      {open && <div className="hz-table-wrap" style={{ marginTop: 6 }}>{children}</div>}
    </div>
  );
}

function Tile({ v, fmt, digits = 0 }: { v: Labelled; fmt: (n: number, d?: number) => string; digits?: number }) {
  return (
    <div className="glass-card hz-tile">
      <div className="hz-tile-value">{v.value == null ? "awaiting data" : `${fmt(v.value, digits)}${v.unit ? ` ${v.unit}` : ""}`}</div>
      <div className="hz-tile-label">{v.label}</div>
      <StatusPill status={v.status} />
      {v.note && <div className="hz-src">{v.note}</div>}
    </div>
  );
}

function DriftChart({ d, fmt }: { d: DriftData; fmt: (n: number, d?: number) => string }) {
  const years = Array.from(new Set(d.rows.map((r) => r.year))).sort();
  const platforms = Array.from(new Set(d.rows.map((r) => r.platform)));
  const colours = [S1, S2];
  const links = platforms.map((p) => {
    const pts = d.rows.filter((r) => r.platform === p);
    return { type: "scatter", mode: "lines", x: pts.map((r) => r.median_lst_h), y: pts.map(() => p), line: { color: "rgba(148,197,255,0.35)", width: 2 }, hoverinfo: "skip" };
  });
  const dots = years.map((yr, i) => {
    const pts = d.rows.filter((r) => r.year === yr);
    return {
      type: "scatter", mode: "markers+text", name: String(yr), x: pts.map((r) => r.median_lst_h), y: pts.map((r) => r.platform),
      marker: { color: colours[i], size: 12, line: { color: "#05080f", width: 2 } },
      text: pts.map((r) => (r.platform === "Aqua" || r.platform === "Terra" ? hhmm(r.median_lst_h) : "")), textposition: "top center",
      textfont: { color: "#e6f1ff", size: 11 },
      customdata: pts.map((r) => [hhmm(r.median_lst_h), fmt(r.n)]),
      hovertemplate: `%{y} · ${yr}<br>median %{customdata[0]} local solar time<br>n = %{customdata[1]} daytime detections<extra></extra>`,
    };
  });
  const xs = d.rows.map((r) => r.median_lst_h).concat(d.nominal_lst_h);
  const ticks: number[] = [];
  for (let h = Math.floor(Math.min(...xs)); h <= Math.ceil(Math.max(...xs)); h++) ticks.push(h);
  return (
    <div className="glass-card hz-chart-card">
      <div className="hz-chart-legend">
        {years.map((y, i) => <span key={y}><span className="hz-sw" style={{ background: colours[i] }} />{y}</span>)}
        <span>┆ design crossing {hhmm(d.nominal_lst_h)}</span>
      </div>
      <div style={{ height: 300 }}>
        <LazyPlot data={[...links, ...dots] as Data[]} config={CONFIG} style={{ width: "100%", height: "100%" }}
          layout={{ ...BASE_LAYOUT, margin: { ...BASE_LAYOUT.margin, l: 90 },
            xaxis: { ...BASE_LAYOUT.xaxis, tickvals: ticks, ticktext: ticks.map(hhmm), range: [Math.min(...xs) - 0.6, Math.max(...xs) + 0.6] },
            shapes: [{ type: "line", x0: d.nominal_lst_h, x1: d.nominal_lst_h, yref: "paper", y0: 0, y1: 1, line: { color: "#94a3b8", dash: "dot", width: 1 } }] } as Partial<Layout>} />
      </div>
      <TableToggle>
        <table className="hz-table"><thead><tr><th>Platform</th><th>Year</th><th>Median local solar time</th><th>Daytime detections</th></tr></thead>
          <tbody>{d.rows.map((r) => <tr key={r.platform + r.year}><td>{r.platform}</td><td>{r.year}</td><td className="num">{hhmm(r.median_lst_h)}</td><td className="num">{fmt(r.n)}</td></tr>)}</tbody></table>
      </TableToggle>
    </div>
  );
}

interface IRow { label: string; value: number; lo?: number | null; hi?: number | null; status: string; colour: string; note?: string }

function IntervalChart({ rows, title, unit, log, reference, intervalLabel, fmt }: { rows: IRow[]; title: string; unit?: string; log?: boolean; reference?: number; intervalLabel: string; fmt: (n: number, d?: number) => string }) {
  const traces = rows.map((r) => ({
    type: "scatter", mode: "markers+text", x: [r.value], y: [r.label],
    marker: { color: r.colour, size: 12, line: { color: "#05080f", width: 2 } },
    error_x: r.lo != null && r.hi != null ? { type: "data", symmetric: false, array: [r.hi - r.value], arrayminus: [r.value - r.lo], color: r.colour, thickness: 2, width: 0 } : undefined,
    text: [fmt(r.value, r.value < 10 ? 2 : 1)], textposition: "top center", textfont: { color: "#e6f1ff", size: 11 },
    hovertemplate: `${r.label}<br>${fmt(r.value, 3)}${unit ? ` ${unit}` : ""}${r.lo != null ? `<br>${intervalLabel}: ${fmt(r.lo, 3)} – ${fmt(r.hi!, 3)}` : ""}<br>status: ${r.status}<extra></extra>`,
  }));
  return (
    <div className="glass-card hz-chart-card">
      <div className="hz-chart-legend"><b style={{ color: "#e6f1ff" }}>{title}</b><span>● estimate</span><span>— {intervalLabel}</span></div>
      <div style={{ height: 70 + rows.length * 56 }}>
        <LazyPlot data={traces as Data[]} config={CONFIG} style={{ width: "100%", height: "100%" }}
          layout={{ ...BASE_LAYOUT, xaxis: { ...BASE_LAYOUT.xaxis, type: log ? "log" : "linear", ...(log ? logTicks(rows) : {}) },
            yaxis: { ...BASE_LAYOUT.yaxis, autorange: "reversed" },
            shapes: reference !== undefined ? [{ type: "line", x0: reference, x1: reference, yref: "paper", y0: 0, y1: 1, line: { color: "#94a3b8", dash: "dot", width: 1 } }] : [] } as Partial<Layout>} />
      </div>
      <TableToggle>
        <table className="hz-table"><thead><tr><th>Item</th><th>Estimate</th><th>{intervalLabel}</th><th>Status</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.label}><td>{r.label}</td><td className="num">{fmt(r.value, 3)}{unit ? ` ${unit}` : ""}</td><td className="num">{r.lo != null ? `${fmt(r.lo, 3)} – ${fmt(r.hi!, 3)}` : "—"}</td><td>{r.status}</td></tr>)}</tbody></table>
      </TableToggle>
    </div>
  );
}

/** 1-2-5 ticks across the data range, so a log axis is not crowded with minor labels. */
function logTicks(rows: IRow[]) {
  const vals = rows.flatMap((r) => [r.value, r.lo ?? r.value, r.hi ?? r.value]);
  const lo = Math.min(...vals) / 1.5, hi = Math.max(...vals) * 1.5;
  const ticks: number[] = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) [1, 2, 5].forEach((m) => { const v = m * 10 ** e; if (v >= lo && v <= hi) ticks.push(v); });
  return { tickvals: ticks, ticktext: ticks.map(String), range: [Math.log10(lo), Math.log10(hi)] };
}

function calibRows(rows: CalibrationRow[], key: "a" | "b"): IRow[] {
  return rows.filter((r) => r.fitted && r[key] != null && (r.version.startsWith("v1") || r.version.startsWith("v2"))).map((r) => ({
    label: `${r.version} (n = ${r.n ?? "?"})`, value: r[key] as number, lo: r[`${key}_interval`]?.[0], hi: r[`${key}_interval`]?.[1],
    status: r.status, colour: r.version.startsWith("v1") ? S2 : S1,
  }));
}

function Body({ d }: { d: SiteData }) {
  const { fmt } = useLanguage();
  const energy = computed<EnergyData>(d.energy);
  const drift = computed<DriftData>(d.drift);
  const cal = computed<CalibrationData>(d.calibration);
  const geo = computed<GeoData>(d.geo_assignment);
  const limits = d.detection_limits.filter((x): x is Labelled => "value" in x && x.value != null);
  const aqua = drift ? drift.rows.filter((r) => r.platform === "Aqua").sort((a, b) => b.year - a.year)[0] : undefined;

  return (
    <>
      <section className="methods">
        <h3>How the harmonized record is built</h3>
        <div className="method-grid">
          {STEPS.map(([title, plain, math], i) => (
            <article key={title} className="method-card glass-card">
              <span className="method-index" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
              <h4>{title}</h4>
              <p>{plain}</p>
              <details className="hz-math"><summary>Show the math</summary><pre>{math}</pre></details>
            </article>
          ))}
        </div>
      </section>

      <section className="hz-block">
        <h3>Energy conservation</h3>
        {energy ? (
          <>
            <div className="hz-tiles">
              <Tile v={energy.before} fmt={fmt} digits={2} />
              <Tile v={energy.after} fmt={fmt} digits={2} />
              <div className="glass-card hz-tile">
                <div className="hz-tile-value">{energy.relative_difference.value?.toExponential(2)}</div>
                <div className="hz-tile-label">{energy.relative_difference.label} ({energy.relative_difference.note})</div>
                <StatusPill status={energy.relative_difference.status} />
              </div>
            </div>
            <p className="hz-src">Source: {energy.before.source}</p>
          </>
        ) : <StatusPill status="awaiting data" />}
      </section>

      <section className="hz-block">
        <h3>Aqua's orbit has drifted</h3>
        {drift ? (
          <>
            <p className="hz-lead">{drift.label}. {aqua ? `In ${aqua.year}, Aqua's median detection time is ${fmt((aqua.median_lst_h - drift.nominal_lst_h) * 60)} minutes after its design crossing time.` : ""} {drift.nominal_note}.</p>
            <DriftChart d={drift} fmt={fmt} />
            <p className="hz-src">Source: {drift.source} · status: {drift.status}</p>
          </>
        ) : <StatusPill status="awaiting data" />}
      </section>

      <section className="hz-block">
        <h3>Calibration v1 (drift-affected) vs v2 (synchronized 2016)</h3>
        {cal ? (
          <>
            <p className="hz-lead"><code>{cal.model}</code> · intervals: {cal.interval}. {cal.why_differ}</p>
            <div className="hz-two">
              <IntervalChart rows={calibRows(cal.rows, "a")} title="Intercept a" intervalLabel="90% interval" reference={0} fmt={fmt} />
              <IntervalChart rows={calibRows(cal.rows, "b")} title="Slope b (1 = same scale)" intervalLabel="90% interval" reference={1} fmt={fmt} />
            </div>
            <div className="glass-card hz-table-wrap" style={{ padding: 12, marginTop: 14 }}>
              <table className="hz-table">
                <thead><tr><th>Version</th><th>n pairs</th><th>a [90%]</th><th>b [90%]</th><th>Status</th><th>Applies to</th></tr></thead>
                <tbody>{cal.rows.map((r) => (
                  <tr key={r.version}><td>{r.version}</td><td className="num">{r.n == null ? "awaiting data" : fmt(r.n)}</td>
                    <td className="num">{r.a == null ? "awaiting data" : `${fmt(r.a, 3)} [${fmt(r.a_interval![0], 3)}, ${fmt(r.a_interval![1], 3)}]`}</td>
                    <td className="num">{r.b == null ? "awaiting data" : `${fmt(r.b, 3)} [${fmt(r.b_interval![0], 3)}, ${fmt(r.b_interval![1], 3)}]`}</td>
                    <td><StatusPill status={r.fitted ? r.status : "awaiting data"} />{!r.fitted && r.reason ? <div className="hz-src">{r.reason}</div> : null}</td>
                    <td>{r.domain}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <p className="hz-src">Source: {cal.source}</p>
          </>
        ) : <StatusPill status="awaiting data" />}
      </section>

      <section className="hz-block">
        <h3>Detection limits</h3>
        <p className="hz-lead">Fire power at which a sensor detects half of the fires (lower = sees smaller fires). The MODIS value is a fitted curve; the Himawari values come from inserting synthetic fires into real images.</p>
        {limits.length > 0 && (
          <IntervalChart log unit="MW" title="50% detection power (log scale)" intervalLabel="interval / tested bracket" fmt={fmt}
            rows={limits.map((x, i) => ({ label: x.label.replace(" 50% detection power", " F50"), value: x.value!, lo: x.interval?.[0], hi: x.interval?.[1], status: x.status, colour: i === 0 ? S1 : S2 }))} />
        )}
        <ul className="hz-list" style={{ marginTop: 10 }}>
          {d.detection_limits.map((x) => ("value" in x && x.value != null
            ? <li key={x.label}><b>{x.label}:</b> {fmt(x.value, 1)} MW <StatusPill status={x.status} /> <span className="hz-src">{x.note} ({x.source})</span></li>
            : <li key={x.label}><b>{x.label}:</b> <StatusPill status="awaiting data" /></li>))}
        </ul>
      </section>

      <section className="hz-block">
        <h3>Geostationary platform assignment</h3>
        {geo ? (
          <div className="hz-two">
            <figure className="hz-figure" style={{ margin: 0 }}>
              <img src={`/${geo.figure}`} alt="World map of the geostationary platform assigned to each grid cell" loading="lazy" />
              <figcaption>{geo.label} <StatusPill status={geo.status} /></figcaption>
            </figure>
            <div className="glass-card hz-table-wrap" style={{ padding: 12 }}>
              <table className="hz-table"><thead><tr><th>Region</th><th>Cells</th><th>Assigned</th><th>Mean view angle</th></tr></thead>
                <tbody>{geo.regions.map((r) => (
                  <tr key={r.region}><td>{r.region}</td><td className="num">{fmt(r.n_cells)}</td>
                    <td>{Object.entries(r.assignment_counts).map(([k, v]) => `${k}: ${fmt(Number(v))}`).join("; ")}</td>
                    <td className="num">{r.mean_selected_vza_deg == null ? "—" : `${fmt(r.mean_selected_vza_deg, 1)}°`}</td></tr>
                ))}</tbody></table>
              <p className="hz-src">Source: {geo.source}</p>
            </div>
          </div>
        ) : <StatusPill status="awaiting data" />}
      </section>

      <section className="hz-block">
        <h3>Northern Australia diurnal investigation <StatusPill status={d.naus.status} /></h3>
        {d.naus.findings ? (
          <>
            <ul className="hz-list">{d.naus.findings.map((f) => <li key={f}>{f}</li>)}</ul>
            {d.naus.published_peak && <p className="hz-lead" style={{ marginTop: 10 }}>{d.naus.published_peak.label}: <b>{fmt(d.naus.published_peak.value!, 2)} h</b> <StatusPill status={d.naus.published_peak.status} /></p>}
            {d.naus.checks && (
              <div className="glass-card hz-table-wrap" style={{ padding: 12 }}>
                <table className="hz-table"><thead><tr><th>Check (one detector-fix round)</th><th>Before</th><th>After</th><th>Result</th></tr></thead>
                  <tbody>{d.naus.checks.map((c) => (
                    <tr key={c.label}><td>{c.label}{c.n_after != null ? <span className="hz-src"> (n {fmt(c.n_before!)} → {fmt(c.n_after)})</span> : null}</td>
                      <td className="num">{fmt(c.before * 100, 1)}%</td><td className="num">{fmt(c.after * 100, 1)}%</td>
                      <td><StatusPill status={c.passed ? "pass" : "fail"} /></td></tr>
                  ))}</tbody></table>
              </div>
            )}
            {d.naus.figure && <figure className="hz-figure" style={{ marginTop: 14 }}><img src={`/${d.naus.figure}`} alt="Northern Australia hourly diagnostics by local solar hour" loading="lazy" /><figcaption>Hourly diagnostics — method demonstration, not applied.</figcaption></figure>}
            <p className="hz-src">Source: {d.naus.source}</p>
          </>
        ) : <StatusPill status="awaiting data" />}
      </section>

      <section className="hz-block">
        <h3>Limitations and awaiting data</h3>
        <div className="glass-card hz-table-wrap" style={{ padding: 12 }}>
          <table className="hz-table"><thead><tr><th>Item</th><th>Effect</th><th>Status</th></tr></thead>
            <tbody>{d.awaiting.map((a) => <tr key={a.item}><td>{a.item}</td><td>{a.effect}</td><td><StatusPill status={a.status} /></td></tr>)}</tbody></table>
        </div>
      </section>

      <section className="hz-block">
        <h3>Data sources</h3>
        <ul className="hz-list">{d.sources.map((s) => <li key={s.name}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> — {s.use}</li>)}</ul>
        <p className="hz-src">Exported from pipeline outputs on {d.exported_utc}.</p>
      </section>
    </>
  );
}

export default function MethodologyPage() {
  const { data, error } = useSiteData();
  const { t } = useLanguage();
  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Harmonized record</p>
          <h2>Methodology & Validation</h2>
          <p className="lead">How the multi-sensor fire record is built and checked. Every number is read from the pipeline's own outputs and carries its status; anything not yet computed says “awaiting data”.</p>
          <HarmonizedProvenance />
        </header>
      </div>
      {data ? <Body d={data} /> : <p className="lead">{error ? `${t("error")}: ${error}` : t("loading")}</p>}
    </main>
  );
}
