import { useMemo } from "react";
import { Link } from "react-router-dom";
import { rng } from "../data";
import { C, Card, Chart, Chip, Legend, PageHead, YGrid, lin, path, smooth } from "../ui";

// --- Data & Methods: full workflow -------------------------------------------------------------

type Stage = { n: string; title: string; q: string; color: string; to: string; w: number; steps: Array<[string, string?]> };
const WORKFLOW: Stage[] = [
  { n: "Foundation", title: "Harmonized record", q: "One comparable record from five satellites", color: C.obs, to: "/methods/harmonization", w: 1.45, steps: [["MODIS + VIIRS", "historical & current collection"], ["Spatial harmonization", "1 km analytical grid"], ["Sensor calibration", "robust, from overlap years"], ["Harmonized observed burning activity"], ["Observation sufficiency & uncertainty"]] },
  { n: "01", title: "Fire Memory", q: "What normally happened here?", color: C.inf, to: "/fire-memory", w: 1.1, steps: [["Burning activity calendar"], ["Current vs. historical"], ["Anomaly detection", "median & MAD"], ["Change points", "PELT"]] },
  { n: "02", title: "Fire Now", q: "What do satellites see now?", color: C.obs, to: "/fire-now", w: 0.9, steps: [["3D globe"], ["Area of interest"], ["Time periods & layers"]] },
  { n: "03", title: "Fire Identity", q: "Which detections are one fire?", color: C.inf, to: "/fire-identity", w: 0.9, steps: [["Event reconstruction", "space-time clustering"], ["Behaviour states", "onset → decaying"]] },
  { n: "04", title: "Fire Evidence", q: "Do independent sources agree?", color: C.ext, to: "/fire-evidence", w: 1.6, steps: [["Reverse geocoding"], ["Regional satellites", "Himawari · GOES · Meteosat · Sentinel · Landsat"], ["Government sources"], ["Country news → NLP extraction"], ["Geographic + temporal matching"], ["Evidence fusion → explainable validation"]] },
  { n: "05", title: "Fire Past", q: "How did similar fires behave?", color: C.inf, to: "/fire-past", w: 0.9, steps: [["Analogue search", "k-NN · Mahalanobis"], ["Duration, expansion, decay"]] },
  { n: "06", title: "Fire Future", q: "Where may new activity be seen?", color: C.fc, to: "/fire-future", w: 1.05, steps: [["Baselines", "persistence · seasonal · wind"], ["LightGBM", "only if it beats baselines"], ["Corridor", "6 · 12 · 24 h"], ["Forecast withheld", "when evidence is thin"]] },
  { n: "07", title: "Exposure", q: "What lies in the corridor?", color: C.fc, to: "/exposure", w: 0.9, steps: [["People & villages"], ["Roads, farms, forests"], ["Schools, hospitals, power"]] },
];
const SOURCES: Array<[string, string]> = [
  ["NASA FIRMS", "MODIS C6.1 · VIIRS 375 m"], ["Himawari-9 · GOES · Meteosat", "geostationary thermal"], ["Sentinel-2 · Landsat", "high-resolution imagery"], ["Copernicus services", "EMS · land cover"],
  ["Government & official", "forest, fire, disaster, weather"], ["Country news & posts", "English-language, NLP"], ["OpenStreetMap", "roads, places, facilities"], ["Population & weather grids", "exposure · forecast inputs"],
];
const FOUR: Array<[string, string, string]> = [["Observation", "What the satellites actually detected", C.obs], ["Inference", "What FlameSeek concludes from it", C.inf], ["External evidence", "What independent sources report", C.ext], ["Forecast", "What may be seen in the next valid window", C.fc]];

export function Workflow() {
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="Data & Methods · full workflow"
        title="Past → Present → Identify → Verify → Compare → Forecast → Exposure"
        sub="How a raw MODIS or VIIRS hotspot becomes an explained, evidence-backed answer."
        right={<><Chip tone={C.obs}>Observation</Chip><Chip tone={C.inf}>Inference</Chip><Chip tone={C.ext}>External evidence</Chip><Chip tone={C.fc}>Forecast</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: WORKFLOW.map((s) => `${s.w}fr`).join(" "), gap: 20 }}>
        {WORKFLOW.map((s, i) => (
          <Card key={s.title} top={s.color} style={{ gap: 8, padding: 12 }}>
            {i > 0 && <span style={{ position: "absolute", left: -15, top: "48%", color: "var(--dim)" }}>›</span>}
            <p className="mono" style={{ fontSize: 8.5, letterSpacing: "0.14em", textTransform: "uppercase", color: s.color }}>{s.n}</p>
            <Link to={s.to}><h3>{s.title}</h3></Link>
            <p className="note" style={{ fontSize: 10.5, minHeight: 30 }}>{s.q}</p>
            {s.steps.map(([step, sub]) => <div key={step} className="inner" style={{ padding: "7px 9px" }}><p style={{ fontSize: 11 }}>{step}</p>{sub && <p className="mono" style={{ fontSize: 8, color: "var(--dim)" }}>{sub}</p>}</div>)}
          </Card>
        ))}
      </div>
      <div className="grid" style={{ gridTemplateColumns: "1.3fr 1fr" }}>
        <Card title="Data sources">
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>{SOURCES.map(([k, v]) => <div key={k} className="inner"><p style={{ fontSize: 11.5, fontWeight: 600 }}>{k}</p><p className="mono" style={{ fontSize: 8.5, color: "var(--dim)" }}>{v}</p></div>)}</div>
        </Card>
        <Card title="Every result keeps four things apart">
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>{FOUR.map(([k, v, c]) => <div key={k} className="inner" style={{ borderLeft: `2px solid ${c}` }}><p className="card-h" style={{ fontSize: 8.5, color: c }}>{k}</p><p style={{ fontSize: 11.5, marginTop: 3 }}>{v}</p></div>)}</div>
        </Card>
      </div>
    </div>
  );
}

// --- Data & Methods: sensor harmonization ------------------------------------------------------

export function Harmonization() {
  const { viirs, scatter, raw, harm } = useMemo(() => {
    const r = rng(41);
    const viirs = Array.from({ length: 22 }, () => [150 + r() * 250, 60 + r() * 220] as [number, number]).filter(([x, y]) => Math.abs(x - 270) / 150 + Math.abs(y - 170) / 130 < 1.15);
    const scatter = Array.from({ length: 420 }, () => {
      const t = r() ** 0.8;
      return [t, t * 0.86 + 0.02 + (r() + r() - 1) * 0.085] as [number, number];
    });
    const harm = Array.from({ length: 23 }, (_, i) => 30 + 12 * Math.sin(i * 0.95) + (i > 10 ? 6 : 0) + r() * 6);
    const raw = harm.map((v, i) => (i < 9 ? v * 1.02 : v * (2.6 + Math.sin(i * 0.9) * 0.9) + (i === 9 ? 20 : 0)));
    return { viirs, scatter, raw, harm };
  }, []);
  const sx = lin(0, 1, 46, 470), sy = lin(0, 1, 250, 14);
  const lx = lin(0, 1, 46, 470), ly = lin(0, 1, 150, 14);
  const logistic = (mid: number) => smooth(Array.from({ length: 30 }, (_, i) => [lx(i / 29), ly(1 / (1 + Math.exp(-(i / 29 - mid) * 14)))] as [number, number]));
  const tx = lin(0, 22, 52, 500), ty = lin(0, 200, 400, 30);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="Data & Methods · sensor harmonization"
        title="From five satellites to one comparable fire record"
        sub="MODIS (1 km) and VIIRS (375 m) see the same fires differently, so their hotspot counts are never simply added together."
        right={<><Chip tone={C.obs}>Input: raw MODIS + VIIRS detections</Chip><Chip tone={C.inf}>Output: Harmonized Observed Burning Activity</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1fr 1fr 1.1fr" }}>
        <div className="col">
          <Card n="01" title="Spatial harmonization" meta="MODIS 1 km grid = analytical grid" className="grow">
            <Chart w={540} h={340}>
              {[0, 1, 2, 3, 4, 5].flatMap((i) => [0, 1, 2, 3].map((j) => {
                const n = viirs.filter(([x, y]) => x >= 30 + i * 80 && x < 110 + i * 80 && y >= 10 + j * 80 && y < 90 + j * 80).length;
                return <g key={`${i}-${j}`}><rect x={30 + i * 80} y={10 + j * 80} width={80} height={80} fill={`rgba(242,139,60,${Math.min(0.5, n * 0.12)})`} stroke="#22344f" />{n > 0 && <text x={102 + i * 80} y={24 + j * 80} textAnchor="end" className="ax" style={{ fill: "#e8eef8" }}>{n}</text>}</g>;
              }))}
              {viirs.map(([x, y], i) => <rect key={i} x={x - 15} y={y - 15} width={30} height={30} fill="rgba(239,83,80,0.8)" stroke="#fda4a4" strokeWidth={0.6} />)}
              <rect x={170} y={70} width={96} height={86} fill="none" stroke="#f2c94c" strokeDasharray="5 4" strokeWidth={1.4} /><rect x={262} y={112} width={100} height={88} fill="none" stroke="#f2c94c" strokeDasharray="5 4" strokeWidth={1.4} />
            </Chart>
            <Legend items={[["1 km analytical cell", "#22344f"], ["VIIRS 375 m pixel", "#ef5350"], ["MODIS 1 km footprint", "#f2c94c"]]} />
            <p className="note" style={{ fontSize: 10.5 }}>VIIRS 375 m pixels are mapped onto the same 1 km cells as MODIS. Each cell then reports activity on one common spatial support.</p>
          </Card>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Card title="Footprint-aware">
              <svg viewBox="0 0 200 76" style={{ width: "100%", height: 76 }}><rect x={20} y={6} width={80} height={64} fill="rgba(242,139,60,0.22)" /><rect x={100} y={6} width={80} height={64} fill="rgba(242,139,60,0.1)" /><rect x={52} y={22} width={84} height={34} fill="none" stroke="#f2c94c" strokeWidth={1.6} /></svg>
              <p className="note" style={{ fontSize: 10.5 }}>Pixel footprint split across cells by overlap: <b className="mono" style={{ color: "var(--text)" }}>0.62 / 0.38</b></p>
            </Card>
            <Card title="Centroid only">
              <svg viewBox="0 0 200 76" style={{ width: "100%", height: 76 }}><rect x={20} y={6} width={160} height={64} fill="none" stroke="#22344f" /><circle cx={100} cy={38} r={24} fill="rgba(90,162,230,0.12)" stroke="#5aa2e6" strokeDasharray="2 3" /><circle cx={100} cy={38} r={3.5} fill="#ef5350" /></svg>
              <p className="note" style={{ fontSize: 10.5 }}>Point kept with its uncertainty radius <b className="mono" style={{ color: "var(--text)" }}>± 0.6 km</b>, never as fully burned land</p>
            </Card>
          </div>
        </div>

        <Card n="02" title="Sensor calibration" meta="overlap period 2012 – 2025">
          <p className="note" style={{ fontSize: 10.5 }}>Matched observations: Aqua MODIS × Suomi NPP VIIRS over the same cell within 20 minutes · n = 48,612</p>
          <Chart w={500} h={280}>
            <line x1={46} x2={470} y1={250} y2={250} stroke="#26364f" /><line x1={46} x2={46} y1={14} y2={250} stroke="#26364f" />
            <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="#3a4a66" strokeDasharray="3 3" /><text x={sx(0.9)} y={sy(0.96)} className="ax">1 : 1</text>
            {scatter.map(([a, b], i) => <circle key={i} cx={sx(a)} cy={sy(Math.max(0, Math.min(1, b)))} r={1.6} fill="#5aa2e6" opacity={0.75} />)}
            <line x1={sx(0.04)} y1={sy(0.055)} x2={sx(1)} y2={sy(0.88)} stroke="#f5b26b" strokeWidth={2.4} />
            {["1", "10", "100", "1k"].map((l, i) => <g key={l}><text x={sx(i / 3)} y={266} textAnchor="middle" className="ax">{l}</text><text x={38} y={sy(i / 3) + 3} textAnchor="end" className="ax">{l}</text></g>)}
            <text x={258} y={278} textAnchor="middle" className="ax">VIIRS fire power per matched cell (MW)</text>
            <text x={12} y={132} textAnchor="middle" className="ax" transform="rotate(-90 12 132)">MODIS fire power (MW)</text>
          </Chart>
          <div className="row wrap"><Chip sm>Robust fit (Theil–Sen)</Chip><Chip sm>slope 0.86 [0.83 – 0.89]</Chip><Chip sm>by land cover & region</Chip></div>
          <p className="card-h">How likely is MODIS to see what VIIRS sees?</p>
          <Chart w={500} h={176}>
            <YGrid ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} y={ly} x0={46} x1={470} fmt={(v) => `${Math.round(v * 100)}%`} />
            <path d={logistic(0.36)} fill="none" stroke={C.ext} strokeWidth={2} /><path d={logistic(0.62)} fill="none" stroke={C.yellow} strokeWidth={2} />
            <text x={lx(0.02)} y={ly(0.72)} className="an" style={{ fill: "var(--ext)" }}>MODIS at nadir · 50% at 5 MW</text><text x={lx(1)} y={ly(0.1)} textAnchor="end" className="an" style={{ fill: "var(--yellow)" }}>MODIS at scan edge · 50% at 32 MW</text>
            {["1", "2", "10", "20", "100", "200"].map((l, i) => <text key={l} x={lx([0.1, 0.22, 0.45, 0.57, 0.83, 0.95][i])} y={166} textAnchor="middle" className="ax">{l}</text>)}
          </Chart>
          <p className="ax" style={{ textAlign: "center", fontFamily: "var(--mono)", fontSize: 9, color: "var(--dim)" }}>fire power seen by VIIRS (MW)</p>
        </Card>

        <div className="col">
          <Card accent={C.inf} n="03" title="Harmonized observed burning activity">
            <p className="big" style={{ fontSize: 30 }}>41.7<small>± 6.2</small></p>
            <p className="note" style={{ fontSize: 10.5 }}>fire-active 1 km cells · Sundarbans Reserve Forest · 1–22 Mar 2026 (MODIS-equivalent)</p>
            <p className="fine">The best comparable estimate from available observations. Not ground truth.</p>
          </Card>
          <Card title="Raw counts vs. harmonized record" meta="annual, Sundarbans Reserve Forest" className="grow">
            <Chart w={540} h={440}>
              <YGrid ticks={[0, 50, 100, 150, 200]} y={ty} x0={52} x1={500} />
              {[[9, "VIIRS joins"], [18, "MODIS orbit drift"]].map(([i, l]) => <g key={l}><line x1={tx(i as number)} x2={tx(i as number)} y1={30} y2={400} stroke="#3a4a66" strokeDasharray="2 3" /><text x={tx(i as number) + 5} y={40} className="ax">{l}</text></g>)}
              <text x={62} y={76} className="an">Raw counts jump in 2012:</text><text x={62} y={90} className="an">a sharper sensor, not more fire</text>
              <path d={path(raw.map((v, i) => [tx(i), ty(v)]))} fill="none" stroke="#9aa7bb" strokeWidth={1.6} />
              <path d={`${smooth(harm.map((v, i) => [tx(i), ty(v * 1.18)]))} ${smooth(harm.map((v, i) => [tx(i), ty(v * 0.82)] as [number, number]).reverse()).replace("M", "L")} Z`} fill="rgba(242,139,60,0.28)" />
              <path d={smooth(harm.map((v, i) => [tx(i), ty(v)]))} fill="none" stroke="#f5b26b" strokeWidth={2.4} />
              {[2005, 2010, 2015, 2020, 2025].map((yr) => <text key={yr} x={tx(yr - 2003)} y={418} textAnchor="middle" className="ax">{yr}</text>)}
            </Chart>
            <Legend items={[["Raw hotspot count (MODIS, then MODIS + VIIRS)", "#9aa7bb"], ["Harmonized, with uncertainty", "#f5b26b"]]} />
          </Card>
        </div>
      </div>
    </div>
  );
}
