import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import DemoGlobe from "../DemoGlobe";
import { BD_OUTLINE, EVENT, SENSORS, inPolygon, rng } from "../data";
import { BdMap, bdProject } from "../maps";
import { C, Card, Chip, KV, Legend, Seg } from "../ui";

// --- 02 · Fire Now: 3D globe --------------------------------------------------------------------

const LAYERS: Array<[string, boolean]> = [["Raw hotspots", true], ["Reconstructed fire events", true], ["Harmonized activity grid", false], ["Observation quality", false], ["Forecast corridors", false]];
const REGIONS: Array<[string, string, string]> = [
  ["Myanmar · Shan State", "Normal", ""], ["Laos · Luang Prabang", "Above normal", C.yellow], ["India · Mizoram", "Normal", ""],
  ["Bangladesh · East Sundarbans", "Highly unusual", C.red], ["Thailand · Chiang Mai", "Above normal", C.yellow],
];

export function FireNowGlobe() {
  const [period, setPeriod] = useState("24 h");
  const [layers, setLayers] = useState(() => LAYERS.map(([, on]) => on));
  const [aoi, setAoi] = useState("Forest area");
  const hourly = useMemo(() => {
    const r = rng(24);
    return Array.from({ length: 48 }, (_, i) => 0.18 + 0.5 * Math.max(0, Math.sin((i / 48) * Math.PI * 4 - 0.6)) ** 2 + r() * 0.16);
  }, []);
  return (
    <div className="stage">
      <DemoGlobe altitude={19_500_000} tooltip={<><p className="card-h" style={{ color: C.inf, fontSize: 8.5 }}>Fire event · expanding</p><b>East Sundarbans, Bangladesh</b><p className="note" style={{ fontSize: 10.5 }}>63 detections · first seen 20 Mar 07:41 UTC</p></>} />

      <div className="dock l" style={{ width: 272, bottom: 92 }}>
        <Card glass>
          <p className="eyebrow" style={{ margin: 0 }}>02 · Fire Now</p>
          <h3>What satellites see now</h3>
          <Seg options={["24 h", "48 h", "7 days", "Historical"]} value={period} onChange={setPeriod} />
          <p className="mono" style={{ fontSize: 9, color: "var(--dim)" }}>21 Mar 14:52 → 22 Mar 14:52 UTC</p>
        </Card>
        <Card glass title="Sensors" meta="detections">
          <div>{SENSORS.map((s) => <KV key={s.name} k={<><i style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: s.color, marginRight: 7 }} />{s.name}</>} v={s.count} />)}</div>
        </Card>
        <Card glass title="Layers">
          <div className="col" style={{ gap: 8 }}>
            {LAYERS.map(([name], i) => (
              <button key={name} type="button" className="row" style={{ background: "none", border: 0, padding: 0, justifyContent: "space-between", fontSize: 11.5 }} onClick={() => setLayers(layers.map((v, j) => (j === i ? !v : v)))}>
                {name}<span className={`tog${layers[i] ? " on" : ""}`} />
              </button>
            ))}
          </div>
        </Card>
        <Card glass title="Area of interest">
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {["Country", "State / division", "District", "Forest area", "Protected area", "Draw polygon"].map((a) => (
              <button key={a} type="button" className="chip" style={{ justifyContent: "flex-start", padding: "6px 9px", ...(a === aoi ? { borderColor: "var(--inf)", color: "var(--text)" } : {}) }} onClick={() => setAoi(a)}>{a}</button>
            ))}
            <Link to="/fire-now/area" className="chip" style={{ gridColumn: "1 / -1", padding: "6px 9px", justifyContent: "flex-start" }}>Radius search · 25 km</Link>
          </div>
        </Card>
      </div>

      <div className="dock r" style={{ width: 304, bottom: 92 }}>
        <Card glass title="At a glance · last 24 h">
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[["18,432", "raw detections", ""], ["2,915", "reconstructed fire events", ""], ["37", "areas flagged unusual", C.yellow], ["11%", "cells with insufficient observation", ""]].map(([v, l, c]) => (
              <div key={l} className="inner"><p className="big" style={{ fontSize: 21, color: c || undefined }}>{v}</p><p className="note" style={{ fontSize: 9.5 }}>{l}</p></div>
            ))}
          </div>
        </Card>
        <Card glass title="Most active regions" meta="vs. seasonal baseline">
          <div>{REGIONS.map(([name, label, tone]) => <div key={name} className="kv" style={{ alignItems: "center" }}><span style={{ color: "var(--soft)" }}>{name}</span><Chip sm tone={tone || undefined}>{label}</Chip></div>)}</div>
        </Card>
        <Card glass accent={C.inf} title="Selected fire event" meta={EVENT.id}>
          <div><h3>{EVENT.place}</h3><p className="note" style={{ fontSize: 10.5 }}>{EVENT.range}</p></div>
          <div className="row wrap"><Chip sm>63 detections · 5 sensors</Chip><Chip sm tone={C.inf}>Expanding</Chip><Chip sm tone={C.ext}>Evidence 88 / 100</Chip></div>
          <Link to="/fire-evidence/case" className="btn primary">Open fire case →</Link>
        </Card>
      </div>

      <Card glass className="float" style={{ left: 16, right: 16, bottom: 14, padding: "8px 14px", gap: 4 }}>
        <div className="row" style={{ justifyContent: "space-between", fontSize: 9, color: "var(--dim)" }}><span className="mono">Detections per hour · global</span><span className="mono">▲ satellite overpass windows</span></div>
        <svg viewBox="0 0 960 34" preserveAspectRatio="none" style={{ width: "100%", height: 34 }}>
          {hourly.map((v, i) => <rect key={i} x={i * 20 + 1} y={30 - v * 34} width={18} height={v * 34} fill={i % 12 > 4 && i % 12 < 9 ? "#3b5c8f" : "#243652"} />)}
          {[4, 13, 19, 28, 32, 43].map((i) => <path key={i} d={`M${i * 20 + 6},34 l4,-4 l4,4z`} fill="#b4c0d4" />)}
        </svg>
      </Card>
    </div>
  );
}

// --- Fire Now · area of interest ----------------------------------------------------------------

const AREA_TYPES: Array<[string, string]> = [
  ["Country", "Bangladesh · 147,570 km²"], ["State / province / division", "Khulna Division"], ["District", "Bagerhat"],
  ["Forest area", "Sundarbans Reserve Forest · ≈6,017 km²"], ["Protected area", "Sundarbans East Wildlife Sanctuary"],
  ["Custom polygon", "Draw on the map, double-click to close"], ["Radius search", "Around a point or fire event · 25 km"],
];
const FOREST: Array<[number, number]> = [[89.05, 22.35], [89.3, 22.5], [89.6, 22.45], [89.9, 22.3], [89.95, 22.0], [89.8, 21.78], [89.4, 21.68], [89.1, 21.72], [89.0, 22.0]];

export function AreaOfInterest() {
  const [type, setType] = useState("Forest area");
  const [period, setPeriod] = useState("7 days");
  const dots = useMemo(() => {
    const r = rng(77);
    const out: Array<{ x: number; y: number; viirs: boolean }> = [];
    const add = (lon: number, lat: number, spread: number, n: number) => {
      for (let i = 0; i < n; i++) {
        const p: [number, number] = [lon + (r() - 0.5) * spread, lat + (r() - 0.5) * spread * 1.3];
        if (inPolygon(p[0], p[1], BD_OUTLINE)) out.push({ x: bdProject(...p)[0], y: bdProject(...p)[1], viirs: r() > 0.45 });
      }
    };
    add(92.2, 22.3, 0.7, 70);
    add(89.3, 25.2, 1.6, 14);
    add(90.6, 24.0, 1.4, 12);
    add(89.2, 24.0, 1.2, 6);
    return out;
  }, []);
  const [ex, ey] = bdProject(EVENT.lon, EVENT.lat);
  return (
    <div className="stage">
      <BdMap>
        <polygon points={FOREST.map(([lon, lat]) => bdProject(lon, lat).join(",")).join(" ")} fill="rgba(160,170,150,0.32)" stroke={C.inf} strokeWidth={1.6} strokeLinejoin="round" />
        <circle cx={ex} cy={ey} r={22} fill="none" stroke="#fda4a4" strokeDasharray="3 3" />
        <circle cx={ex} cy={ey} r={9} fill="rgba(239,83,80,0.85)" stroke="#fff" strokeWidth={0.8} />
        <text x={ex + 27} y={ey + 3} className="map-label">25 km radius</text>
        <text x={bdProject(89.45, 21.55)[0]} y={bdProject(89.45, 21.55)[1]} textAnchor="middle" className="map-caps">SUNDARBANS RESERVE FOREST</text>
        {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={2.3} fill={d.viirs ? "#ef5350" : "#f2c94c"} />)}
      </BdMap>

      <div className="dock l" style={{ width: 312 }}>
        <Card glass>
          <p className="eyebrow" style={{ margin: 0 }}>Area of interest</p>
          <h3>Choose where to analyse</h3>
          <div className="inner row" style={{ justifyContent: "space-between" }}><span>⌕&nbsp; Sundarbans</span><span className="mono" style={{ fontSize: 9, color: "var(--dim)" }}>4 matches</span></div>
          <p className="note" style={{ fontSize: 10.5 }}>Bangladesh › Khulna Division › Bagerhat · Khulna · Satkhira › <b style={{ color: "var(--text)" }}>Sundarbans Reserve Forest</b></p>
        </Card>
        <Card glass title="Area type" className="grow">
          <div className="col" style={{ gap: 7 }}>
            {AREA_TYPES.map(([name, sub]) => (
              <button key={name} type="button" className={`opt${name === type ? " on" : ""}`} onClick={() => setType(name)}><span><b>{name}</b><small>{sub}</small></span></button>
            ))}
          </div>
        </Card>
      </div>

      <div className="dock r" style={{ width: 322 }}>
        <Card glass accent={C.obs} title="Selected area" meta={<Chip sm>{type}</Chip>}>
          <div><h3>Sundarbans Reserve Forest</h3><p className="note" style={{ fontSize: 10.5 }}>Bangladesh part · Khulna Division</p></div>
          <div>
            <KV k="Hotspot detections · 24 h" v="41" />
            <KV k="Hotspot detections · 7 days" v="63" />
            <KV k="Active fire events" v="1" />
            <KV k="Harmonized activity vs. March baseline" v="4.1×" color={C.red} />
            <KV k="Observation sufficiency · 24 h" v="0.78" />
            <KV k="Last valid observation" v="NOAA-21 · 14:05 UTC" />
          </div>
        </Card>
        <Card glass title="Analyse this area">
          <Link to="/fire-memory" className="btn primary">Build fire memory · 2003–2026</Link>
          <Link to="/fire-memory/anomaly" className="btn">Compare now with history</Link>
          <Link to="/fire-identity" className="btn">Show fire events in this area</Link>
        </Card>
        <Card glass title="Time period"><Seg options={["24 h", "7 days", "Season", "2003–now"]} value={period} onChange={setPeriod} /></Card>
      </div>

      <Card glass className="float" style={{ left: 344, bottom: 14, padding: "8px 12px" }}>
        <Legend items={[["VIIRS", "#ef5350"], ["MODIS", "#f2c94c"], ["Forest outline (approx.)", "rgba(160,170,150,0.6)"], ["Selected area", C.inf]]} />
      </Card>
    </div>
  );
}

// --- Fire Now · observation quality & uncertainty ----------------------------------------------

const STATUS: Array<[string, string, string]> = [
  ["Reliable multi-sensor observation", "#3ecf8e", "14%"], ["Valid observation, no fire detected", "#2f4f7f", "47%"], ["Cloud-covered or low quality", "#9aa7bb", "21%"],
  ["Missing satellite observation", "#3a3f4d", "7%"], ["Sensor disagreement", "#f2c94c", "6%"], ["Limited evidence", "#a78bfa", "5%"],
];
const OVERPASSES: Array<[string, string, string, string]> = [
  ["MODIS Terra", "04:15 UTC", "cloud", ""], ["VIIRS NOAA-21", "07:05 UTC", "clear · heat", C.ext], ["VIIRS Suomi NPP", "07:30 UTC", "cloud", ""],
  ["VIIRS NOAA-20", "07:55 UTC", "clear · no heat", C.obs], ["MODIS Aqua", "09:40 UTC", "off-swath", ""], ["MODIS Terra", "15:20 UTC", "cloud", ""],
];

export function ObservationQuality() {
  const cells = useMemo(() => {
    const r = rng(5);
    const out: Array<{ x: number; y: number; s: number; w: number; h: number }> = [];
    const step = 0.16;
    for (let lat = 20.6; lat < 26.7; lat += step) {
      for (let lon = 88.0; lon < 92.7; lon += step) {
        if (!inPolygon(lon + step / 2, lat + step / 2, BD_OUTLINE)) continue;
        let s = 1;
        const v = r();
        if (lon < 89.25 && lat > 23.0 && lat < 26.0) s = 3;
        else if (Math.hypot(lon - 90.3, (lat - 24.3) * 1.2) < 0.75 || (lon > 91.4 && lat < 22.5 && v > 0.45) || (lat > 25.4 && lon > 88.9 && v > 0.5)) s = 2;
        else if (lon > 91.9 && lat < 23.2 && v > 0.35) s = v > 0.7 ? 0 : 4;
        else if (Math.hypot(lon - 89.8, lat - 22.1) < 0.28) s = 0;
        else if (v > 0.95) s = 4;
        else if (v > 0.91) s = 5;
        const [x, y] = bdProject(lon, lat + step);
        out.push({ x, y, s, w: step * 90.9, h: step * 98.6 });
      }
    }
    return out;
  }, []);
  const sel = bdProject(92.08, 22.62);
  return (
    <div className="stage">
      <BdMap cities fill="#0f1a2e">
        {cells.map((c, i) => <rect key={i} x={c.x} y={c.y} width={c.w - 0.8} height={c.h - 0.8} fill={STATUS[c.s][1]} opacity={c.s === 1 ? 0.85 : 0.95} />)}
        <rect x={sel[0]} y={sel[1]} width={14} height={15} fill="none" stroke="#fff" strokeWidth={1.8} />
        <line x1={sel[0] + 14} y1={sel[1] + 7} x2={BD_W_EDGE} y2={sel[1] - 70} stroke="#fff" strokeDasharray="2 3" opacity={0.7} />
      </BdMap>

      <div className="dock l" style={{ width: 312 }}>
        <Card glass>
          <p className="eyebrow" style={{ margin: 0 }}>Observation quality & uncertainty</p>
          <h3>Was each place really seen?</h3>
          <p className="note">No hotspot does not always mean no fire. Every 1 km cell records how well it was observed in the last 24 h.</p>
        </Card>
        <Card glass title="Observation status · 24 h" meta="share of cells">
          <div className="col" style={{ gap: 9 }}>
            {STATUS.map(([label, color, share]) => (
              <div key={label} className="row" style={{ fontSize: 11.5 }}><i style={{ width: 12, height: 12, borderRadius: 3, background: color, flex: "none" }} /><span style={{ color: "var(--soft)" }}>{label}</span><span className="mono right" style={{ fontSize: 10, color: "var(--dim)" }}>{share}</span></div>
            ))}
          </div>
        </Card>
        <Card glass title="When evidence is not enough" className="grow">
          {[["UNKNOWN", "Not observed by any sensor in the window."], ["AMBIGUOUS", "Sensors disagree and no external source settles it."], ["INSUFFICIENT OBSERVATION", "Seen, but cloud or poor geometry make “no fire” unreliable."]].map(([k, v]) => (
            <div key={k} className="inner"><p className="mono" style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: C.yellow }}>{k}</p><p className="note" style={{ fontSize: 10.5 }}>{v}</p></div>
          ))}
          <p className="fine">FlameSeek shows these instead of declaring “no fire”.</p>
        </Card>
      </div>

      <div className="dock r" style={{ width: 340 }}>
        <Card glass accent={C.obs} title="Cell inspector" meta="cell BD-1km-22.716-92.186" className="grow">
          <div><h3>Rangamati Hill District, Chattogram</h3><p className="note" style={{ fontSize: 10.5 }}>22 Mar 2026 · last 24 h · 6 overpass opportunities</p></div>
          <div className="inner" style={{ borderColor: "rgba(242,201,76,0.4)", background: "rgba(242,201,76,0.06)" }}>
            <p className="mono" style={{ fontWeight: 700, letterSpacing: "0.12em", color: C.yellow }}>INSUFFICIENT OBSERVATION</p>
            <p className="note" style={{ fontSize: 10.5 }}>2 of 6 passes clear. A fire here could have been missed; FlameSeek does not report “no fire”.</p>
          </div>
          <p className="card-h">Observation sufficiency score</p>
          <div style={{ position: "relative", height: 26 }}>
            <div style={{ height: 6, borderRadius: 3, background: "linear-gradient(90deg,#ef5350,#f2c94c 45%,#3ecf8e)" } as CSSProperties} />
            <i style={{ position: "absolute", left: "31%", top: -3, width: 3, height: 12, background: "#fff", borderRadius: 2 }} />
            <span className="mono" style={{ position: "absolute", left: "31%", top: 12, transform: "translateX(-50%)", fontSize: 10.5 }}>0.31</span>
          </div>
          <div>
            <KV k="Sensor agreement" v="1 of 2 clear sensors detect heat" />
            <KV k="Data quality" v="Cloud 67% · smoke likely" />
            <KV k="Uncertainty range" v="0 – 3.4 fire-active cells" />
            <KV k="Data source" v="NASA FIRMS · NRT" />
            <KV k="Sensors" v="MODIS Terra · VIIRS NOAA-20, NOAA-21" />
            <KV k="Processing method" v="Harmonization v1.3 · robust calibration" />
            <KV k="Provenance" v="VJ214IMG · VJ114IMG · MOD14" />
          </div>
          <p className="card-h">Overpasses in window</p>
          <div>{OVERPASSES.map(([sat, time, state, tone], i) => <div key={i} className="kv" style={{ alignItems: "center" }}><span style={{ color: "var(--soft)", minWidth: 110 }}>{sat}</span><span className="mono" style={{ fontSize: 10 }}>{time}</span><Chip sm tone={tone || undefined}>{state}</Chip></div>)}</div>
        </Card>
      </div>
    </div>
  );
}

const BD_W_EDGE = 1000;
