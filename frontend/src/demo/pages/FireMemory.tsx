import { useState } from "react";
import { Link } from "react-router-dom";
import { ANNUAL, CALENDAR, MONTHS, YEARS } from "../data";
import { C, Card, Chart, Chip, PageHead, Seg, YGrid, lin, path, smooth } from "../ui";

// --- 01 · Fire Memory: burning activity calendar -----------------------------------------------

const heat = (v: number) => (v < 0 ? "transparent" : v > 30 ? "#ffd9a0" : `rgba(242,139,60,${Math.min(1, 0.07 + v / 15).toFixed(2)})`);
const PROFILE = [0.8, 1.6, 9.6, 12.5, 6.4, 0.9, 0.1, 0.05, 0.05, 0.2, 0.4, 0.6];
const STATS: Array<[string, string, string]> = [
  ["Hotspot frequency", "9.6", "fire-cell days · 6.1 – 15.2"], ["Fire radiative power", "18 MW", "per detection · 9 – 34"], ["Spatial spread", "2.1 km²", "per event · 0.8 – 4.6"],
  ["Event duration", "1.8 days", "0.6 – 3.9"], ["Active days per year", "14", "days · 8 – 21"], ["Seasonal peak", "Apr 6 – 20", "median peak window"],
];

export function BurningCalendar() {
  const [span, setSpan] = useState("2003–2026");
  const first = span === "5 yrs" ? YEARS.length - 5 : span === "10 yrs" ? YEARS.length - 10 : 0;
  const years = YEARS.slice(first);
  const totals = CALENDAR.map((row) => row.reduce((a, b) => a + Math.max(0, b), 0));
  const maxTotal = Math.max(...totals);
  const py = lin(0, 40, 104, 8);
  const ay = lin(0, 80, 96, 6);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="01 · Fire Memory"
        title="What normally happens in the Sundarbans Reserve Forest?"
        sub="23 years of harmonized MODIS + VIIRS activity for the selected area. Each square is one month of one year."
        right={<><div style={{ width: 210 }}><Seg options={["5 yrs", "10 yrs", "2003–2026"]} value={span} onChange={setSpan} /></div><Chip>MODIS + VIIRS · harmonized</Chip><Link to="/fire-now/area" className="btn inline">Change area</Link></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1.75fr 1fr" }}>
        <Card title="Burning activity calendar" meta="harmonized fire-active 1 km cells per month">
          <div className="grow" style={{ display: "grid", gridTemplateColumns: "34px repeat(12, 1fr) 96px", gridAutoRows: "minmax(11px, 1fr)", gap: 2, alignItems: "stretch", fontSize: 9, minHeight: years.length * 13 }}>
            <span />
            {MONTHS.map((m) => <span key={m} className="mono" style={{ textAlign: "center", color: "var(--dim)" }}>{m}</span>)}
            <span className="mono" style={{ color: "var(--dim)", paddingLeft: 8 }}>year total</span>
            {years.map((year, i) => {
              const row = CALENDAR[first + i];
              return [
                <span key={year} className="mono" style={{ color: year === 2026 ? "var(--text)" : "var(--dim)", fontWeight: year === 2026 ? 700 : 400, alignSelf: "center" }}>{year}</span>,
                ...row.map((v, m) => <span key={`${year}-${m}`} title={v >= 0 ? `${MONTHS[m]} ${year}: ${v}` : ""} style={{ background: heat(v), borderRadius: 2, border: v < 0 ? "0" : "1px solid rgba(255,255,255,0.02)" }} />),
                <span key={`${year}-t`} style={{ paddingLeft: 8, display: "flex", alignItems: "center" }}><i style={{ display: "block", height: "62%", minHeight: 5, width: `${(totals[first + i] / maxTotal) * 100}%`, background: year === 2026 ? "var(--red)" : "#3b5c8f", borderRadius: 2 }} /></span>,
              ];
            })}
          </div>
          <p className="mono" style={{ fontSize: 9.5, color: "var(--soft)" }}>◀ March 2026 so far: 39.4 (median 9.6)</p>
          <p className="card-h">Seasonal profile · median and typical range</p>
          <svg viewBox="0 0 900 122" style={{ width: "100%", height: 122, flex: "none" }}>
            <YGrid ticks={[0, 10, 20, 30, 40]} y={py} x0={34} x1={880} />
            {PROFILE.map((v, m) => {
              const x = 34 + (m + 0.5) * 70.5;
              return (
                <g key={m}>
                  <rect x={x - 24} y={py(v * 1.45)} width={48} height={Math.max(2, py(v * 0.6) - py(v * 1.45))} fill="rgba(242,139,60,0.28)" rx={1.5} />
                  <rect x={x - 24} y={py(v) - 1.2} width={48} height={2.4} fill={C.inf} />
                  <text x={x} y={118} textAnchor="middle" className="ax">{MONTHS[m]}</text>
                </g>
              );
            })}
            <circle cx={34 + 2.5 * 70.5} cy={py(39.4)} r={4.5} fill={C.red} />
            <text x={34 + 2.5 * 70.5 + 12} y={py(39.4) + 3.5} className="an">2026</text>
          </svg>
        </Card>

        <div className="col">
          <Card accent={C.inf} title="The fire season here">
            <p style={{ fontSize: 13 }}>Burning is concentrated in <b>March – May</b>, the dry months before the monsoon. Almost no activity from <b>June to November</b>.</p>
            <div className="row wrap"><Chip sm tone={C.yellow}>Peak: April</Chip><Chip sm tone={C.obs}>Quiet: Jun – Nov</Chip><Chip sm tone={C.red}>Mar 2026: 4.1× median</Chip></div>
          </Card>
          <Card title="Seasonal fire profile · March" meta="median · typical range (IQR)" className="grow">
            <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {STATS.map(([k, v, s]) => <div key={k} className="inner"><p className="note" style={{ fontSize: 10 }}>{k}</p><p className="big" style={{ fontSize: 20, margin: "3px 0" }}>{v}</p><p className="mono" style={{ fontSize: 8.5, color: "var(--dim)" }}>{s}</p></div>)}
            </div>
            <p className="card-h">Annual activity</p>
            <svg viewBox="0 0 500 112" style={{ width: "100%", flex: 1, minHeight: 80 }}>
              <YGrid ticks={[0, 20, 40, 60, 80]} y={ay} x0={26} x1={490} />
              {ANNUAL.map((v, i) => <rect key={i} x={30 + i * 20} y={ay(v)} width={15} height={96 - ay(v)} fill="#3b5c8f" />)}
              {[2003, 2008, 2013, 2018, 2025].map((yr) => <text key={yr} x={37 + (yr - 2003) * 20} y={108} textAnchor="middle" className="ax">{yr}</text>)}
            </svg>
          </Card>
          <Link to="/fire-memory/anomaly" className="btn primary">Compare current activity with history →</Link>
        </div>
      </div>
    </div>
  );
}

// --- Fire Memory · current vs. historical (anomaly + change point) -----------------------------

const CATEGORIES: Array<[string, string, string]> = [["Normal", "|z| < 1.5", "#5b7393"], ["Above normal", "1.5 – 2.5", "#d9b13b"], ["Unusual", "2.5 – 3.5", "#f28b3c"], ["Highly unusual", "> 3.5", "#ef5350"]];
const FLAGS: Array<[boolean, string, string]> = [
  [true, "More hotspots than normal", "39.4 · median 9.6"], [true, "Unusually strong fire power", "96 MW · 90th pct 34"], [false, "Fire outside the normal season", "no · March is in season"],
  [true, "Rapid spatial expansion", "4.8 → 12.6 km² · 24 h"], [true, "Repeated detections over a long period", "3 days · 9 passes"], [true, "Sudden increase in burning activity", "+310% · 48 h"],
];

export function Anomaly() {
  const x = lin(0, 120, 46, 600);
  const y = lin(0, 70, 232, 12);
  const days = Array.from({ length: 25 }, (_, i) => i * 5);
  const median = (d: number) => 41 * (d / 120) ** 2.3;
  const band = (k: number) => `${path(days.map((d) => [x(d), y(median(d) * (1 + 0.09 * k * (0.4 + d / 120)))]))} ${path(days.slice().reverse().map((d) => [x(d), y(median(d) * (1 - 0.09 * k * (0.4 + d / 120)))])).replace("M", "L")} Z`;
  const now: Array<[number, number]> = [[0, 0], [14, 0.6], [28, 2.2], [40, 4.1], [44, 12], [47, 25], [50, 38]];
  const by = lin(0, 80, 222, 16);
  const before = ANNUAL.slice(0, 11), after = ANNUAL.slice(11);
  const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="01 · Fire Memory · current vs. historical"
        title="Is this season normal for the Sundarbans?"
        sub="Current harmonized activity compared with the same dates in 2003–2025, using robust statistics that are not skewed by a few extreme years."
        right={<><Chip>Baseline: median & MAD · 2003–2025</Chip><Chip>Change points: PELT</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1.65fr 1fr" }}>
        <div className="col">
          <Card title="This season vs. history" meta="cumulative harmonized fire-active cells since 1 Feb" className="grow">
            <Chart w={760} h={260}>
              <YGrid ticks={[0, 10, 20, 30, 40, 50, 60, 70]} y={y} x0={46} x1={600} />
              {[3, 2, 1].map((k) => <path key={k} d={band(k)} fill="rgba(90,162,230,0.16)" />)}
              <path d={smooth(days.map((d) => [x(d), y(median(d))]))} fill="none" stroke="#bcd9f7" strokeWidth={2} />
              <line x1={x(50)} x2={x(50)} y1={12} y2={232} stroke="#3a4a66" strokeDasharray="2 3" />
              <path d={path(now.map(([d, v]) => [x(d), y(v)]))} fill="none" stroke={C.red} strokeWidth={2.2} />
              <circle cx={x(50)} cy={y(38)} r={4.5} fill={C.red} />
              <text x={x(50) + 9} y={y(38) + 3.5} className="an">2026 · today, robust z = +4.6</text>
              {[["1 Feb", 0], ["1 Mar", 28], ["1 Apr", 59], ["1 May", 89], ["31 May", 120]].map(([l, d]) => <text key={l} x={x(d as number)} y={248} textAnchor="middle" className="ax">{l}</text>)}
              {[["Median 2003–2025", "#bcd9f7"], ["± 1, 2, 3 MAD bands", "#3d6ea5"], ["2026", C.red]].map(([l, c], i) => <g key={l}><rect x={628} y={24 + i * 18} width={12} height={3} fill={c} /><text x={646} y={28 + i * 18} className="an">{l}</text></g>)}
            </Chart>
          </Card>
          <Card title="Long-term change · statistically detected change points" meta="annual activity, 2003–2025" className="grow">
            <Chart w={760} h={246}>
              <YGrid ticks={[0, 20, 40, 60, 80]} y={by} x0={46} x1={640} />
              {ANNUAL.map((v, i) => <rect key={i} x={52 + i * 25.4} y={by(v)} width={19} height={222 - by(v)} fill={i < 11 ? "#3b5c8f" : "#6b4f9e"} />)}
              <line x1={329} x2={329} y1={8} y2={222} stroke={C.inf} strokeDasharray="3 3" />
              <text x={335} y={18} className="an">change point · 2014</text>
              <line x1={52} x2={329} y1={by(mean(before))} y2={by(mean(before))} stroke="#bcd9f7" strokeWidth={1.6} />
              <line x1={329} x2={636} y1={by(mean(after))} y2={by(mean(after))} stroke="#d6c7fb" strokeWidth={1.6} />
              <text x={650} y={by(mean(after)) + 3} className="an">mean after (+{Math.round((mean(after) / mean(before) - 1) * 100)}%)</text>
              <text x={650} y={by(mean(before)) + 3} className="an">mean before</text>
              {[2003, 2006, 2009, 2012, 2014, 2017, 2020, 2023].map((yr) => <text key={yr} x={61 + (yr - 2003) * 25.4} y={238} textAnchor="middle" className="ax">{yr}</text>)}
            </Chart>
          </Card>
        </div>
        <div className="col">
          <Card accent={C.inf} title="Anomaly category" meta="robust z = +4.6">
            <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 4 }}>
              {CATEGORIES.map(([label, range, color], i) => (
                <div key={label} style={{ textAlign: "center" }}>
                  <div style={{ background: color, color: "#10151f", fontWeight: 700, fontSize: 10.5, padding: "7px 2px", borderRadius: 5, outline: i === 3 ? "2px solid #fff" : "none", opacity: i === 3 ? 1 : 0.8 }}>{label}</div>
                  <p className="mono" style={{ fontSize: 8.5, color: "var(--dim)", marginTop: 5 }}>{range}</p>
                </div>
              ))}
            </div>
            <p className="fine">Labels describe statistical behaviour compared with this place's history, not disaster severity.</p>
          </Card>
          <Card title="Why it was flagged" meta="now · typical for 22 Mar" className="grow">
            <div>
              {FLAGS.map(([hit, label, detail]) => (
                <div key={label} className="kv" style={{ padding: "9px 0" }}><span style={{ color: hit ? "var(--text)" : "var(--dim)" }}><b style={{ color: hit ? C.red : "var(--dim)", marginRight: 10 }}>{hit ? "✓" : "–"}</b>{label}</span><b style={{ color: "var(--muted)" }}>{detail}</b></div>
              ))}
            </div>
          </Card>
          <Card title="Change point found">
            <p style={{ fontSize: 13 }}>Average yearly activity rose by about <b>{Math.round((mean(after) / mean(before) - 1) * 100)}%</b> from 2014 onwards.</p>
            <p className="fine">A statistically detected change. Possible reasons (land use, climate, reporting) are not established by this test.</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
