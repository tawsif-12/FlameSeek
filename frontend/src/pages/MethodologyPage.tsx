import { useEffect, useState } from "react";
import { CalibrationData, CalibrationRow, computed, DriftData, EnergyData, GeoData, Labelled, SiteData, useSiteData } from "../api/harmonized";
import { useLanguage } from "../context/LanguageContext";
import HarmonizedProvenance, { StatusPill } from "../components/HarmonizedProvenance";
import { CoverageCautionButton } from "../components/DataCoverageNotice";
import HarmonizedStepsDeck from "../components/HarmonizedStepsDeck";
import { AnimatedDriftChart, AnimatedIntervalChart, type IntervalChartRow } from "../components/AnimatedMethodologyCharts";
import "../harmonized.css";

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
  return (
    <AnimatedDriftChart d={d} fmt={fmt}>
      <TableToggle>
        <table className="hz-table"><thead><tr><th>Platform</th><th>Year</th><th>Median local solar time</th><th>Daytime detections</th></tr></thead>
          <tbody>{d.rows.map((r) => <tr key={r.platform + r.year}><td>{r.platform}</td><td>{r.year}</td><td className="num">{hhmm(r.median_lst_h)}</td><td className="num">{fmt(r.n)}</td></tr>)}</tbody></table>
      </TableToggle>
    </AnimatedDriftChart>
  );
}

type IRow = IntervalChartRow;

function IntervalChart({ rows, title, unit, log, reference, intervalLabel, fmt }: { rows: IRow[]; title: string; unit?: string; log?: boolean; reference?: number; intervalLabel: string; fmt: (n: number, d?: number) => string }) {
  return (
    <AnimatedIntervalChart rows={rows} title={title} unit={unit} log={log} reference={reference} intervalLabel={intervalLabel} fmt={fmt}>
      <TableToggle>
        <table className="hz-table"><thead><tr><th>Item</th><th>Estimate</th><th>{intervalLabel}</th><th>Status</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.label}><td>{r.label}</td><td className="num">{fmt(r.value, 3)}{unit ? ` ${unit}` : ""}</td><td className="num">{r.lo != null ? `${fmt(r.lo, 3)} – ${fmt(r.hi!, 3)}` : "—"}</td><td>{r.status}</td></tr>)}</tbody></table>
      </TableToggle>
    </AnimatedIntervalChart>
  );
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
      <section className="pt-methods-section" aria-label="How the harmonized record is built">
        <HarmonizedStepsDeck steps={STEPS} />
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
        {d.naus.checks || d.naus.figure ? (
          <>
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
  const [coverageOpen, setCoverageOpen] = useState(false);

  useEffect(() => {
    if (!coverageOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCoverageOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [coverageOpen]);

  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> Harmonized record</p>
          <div className="hz-title-caution-row">
            <h2>Methodology & Validation</h2>
            <CoverageCautionButton
              open={coverageOpen}
              onToggle={() => setCoverageOpen((open) => !open)}
              controlsId="methodology-coverage-notice"
            />
          </div>
          <p className="lead">How the multi-sensor fire record is built and checked. Every number is read from the pipeline's own outputs and carries its status; anything not yet computed says “awaiting data”.</p>
          <HarmonizedProvenance
            showNotice={coverageOpen}
            noticeId="methodology-coverage-notice"
            onCloseNotice={() => setCoverageOpen(false)}
          />
        </header>
      </div>
      {data ? <Body d={data} /> : <p className="lead">{error ? `${t("error")}: ${error}` : t("loading")}</p>}
    </main>
  );
}
