import { useState } from "react";
import type { CSSProperties } from "react";
import { EVENT } from "../data";
import { Corridor, EVT, EventDot, LocalMap } from "../maps";
import { Bar, C, Card, Chart, Chip, KV, Legend, PageHead, Seg, lin, smooth } from "../ui";

// --- 05 · Fire Past: historical analogues ------------------------------------------------------

const ANALOGUES: Array<[string, string, string, string, string, boolean, string, string, string]> = [
  ["FS-BD-2021-0388", "Sharankhola Range", "May 2021", "0.41", "5.5 d", true, "118 MW", "day 4", "4.2 km²"],
  ["FS-BD-2016-0207", "Chandpai Range", "Mar 2016", "0.58", "3.0 d", false, "71 MW", "day 2", "1.6 km²"],
  ["FS-BD-2019-0311", "Sharankhola Range", "Apr 2019", "0.63", "6.8 d", true, "134 MW", "day 4", "5.9 km²"],
  ["FS-BD-2014-0156", "Chandpai Range", "Mar 2014", "0.77", "4.5 d", true, "88 MW", "day 3", "2.8 km²"],
  ["FS-BD-2023-0402", "Sharankhola Range", "Apr 2023", "0.82", "4.0 d", true, "102 MW", "day 3", "3.3 km²"],
];
const WEIGHTS: Array<[string, number]> = [["Season", 0.9], ["Ecological region", 1], ["Duration", 0.6], ["Fire power", 0.75], ["Expansion", 0.8], ["Persistence", 0.55], ["Weather", 0.65], ["Behaviour", 0.7]];
// [duration days, peak MW, peak day]
const CURVES: Array<[number, number, number]> = [[5.5, 118, 3.4], [3.0, 71, 1.7], [6.8, 134, 3.6], [4.5, 88, 2.4], [4.0, 102, 2.6]];

export function FirePast() {
  const [sel, setSel] = useState(0);
  const x = lin(0, 7, 60, 800);
  const y = lin(0, 150, 250, 16);
  const curve = ([dur, peak, at]: [number, number, number]) =>
    smooth(Array.from({ length: 15 }, (_, i) => {
      const d = (dur * i) / 14;
      return [x(d), y(4 + peak * Math.max(0, 1 - ((d - at) / (d < at ? at : dur - at + 1.2)) ** 2))] as [number, number];
    }));
  const now: Array<[number, number]> = [[0, 12], [0.3, 9], [0.6, 16], [0.9, 22], [1.1, 36], [1.4, 30], [1.6, 44], [1.85, 64], [2, 96]];
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="05 · Fire Past · historical analogues"
        title="How did similar fires behave before?"
        sub="The current event is compared with 23 years of reconstructed fire events to find its closest historical analogues."
        right={<><Chip>k-nearest neighbours · k = 5</Chip><Chip>Mahalanobis distance</Chip><Chip>4,812 past events searched</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "0.6fr 2.2fr" }}>
        <Card accent={C.inf} title="Current event profile" meta={EVENT.id}>
          <div>
            <KV k="Season" v="March · dry season" /><KV k="Ecological region" v="Sundarbans mangroves" /><KV k="Duration so far" v="2.0 days" /><KV k="Peak fire power" v="96 MW" />
            <KV k="Spatial expansion" v="+162% / 24 h" /><KV k="Persistence" v="9 passes · 3 days" /><KV k="Weather" v="RH 48% · SW 12 km/h" /><KV k="Behaviour state" v="Expanding" color={C.inf} />
          </div>
          <p className="card-h">Feature weights</p>
          <div className="col" style={{ gap: 9 }}>{WEIGHTS.map(([k, v]) => <div key={k} className="row" style={{ fontSize: 10.5, color: "var(--muted)" }}><span style={{ width: 104 }}>{k}</span><Bar value={v} color={C.obs} /></div>)}</div>
        </Card>
        <div className="col">
          <Card title="Closest historical analogues" meta="smaller distance = more similar">
            <table className="tbl">
              <thead><tr><th>Event</th><th>Place</th><th>Start</th><th className="n">Distance</th><th className="n">Duration</th><th>Expanded?</th><th className="n">Peak FRP</th><th className="n">Decay began</th><th className="n">Burned area</th></tr></thead>
              <tbody>
                {ANALOGUES.map(([id, place, start, dist, dur, exp, frp, decay, area], i) => (
                  <tr key={id} className={i === sel ? "hl" : ""} style={{ cursor: "pointer" }} onClick={() => setSel(i)}>
                    <td className="mono" style={{ fontSize: 10.5 }}>{id}</td><td>{place}</td><td>{start}</td><td className="n">{dist}</td><td className="n">{dur}</td><td><Chip sm tone={exp ? C.yellow : C.obs}>{exp ? "yes" : "no"}</Chip></td><td className="n">{frp}</td><td className="n">{decay}</td><td className="n">{area}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Fire power over time · analogues vs. now" meta="days since first detection" className="grow">
            <Chart w={1000} h={280}>
              {[0, 50, 100].map((v) => <g key={v}><line x1={60} x2={800} y1={y(v)} y2={y(v)} stroke="#162238" /><text x={52} y={y(v) + 3} textAnchor="end" className="ax">{v} MW</text></g>)}
              {CURVES.map((c, i) => i !== sel && <path key={i} d={curve(c)} fill="none" stroke="#51688c" strokeWidth={1.3} />)}
              <path d={curve(CURVES[sel])} fill="none" stroke="#cfe3fb" strokeWidth={2.4} />
              <line x1={x(2)} x2={x(2)} y1={16} y2={250} stroke="#3a4a66" strokeDasharray="2 3" /><text x={x(2) + 6} y={24} className="an">now · day 2</text>
              <path d={smooth(now.map(([d, v]) => [x(d), y(v)]))} fill="none" stroke={C.inf} strokeWidth={2.6} /><circle cx={x(2)} cy={y(96)} r={4.5} fill={C.inf} />
              {Array.from({ length: 8 }, (_, d) => <text key={d} x={x(d)} y={268} textAnchor="middle" className="ax">day {d}</text>)}
              {[["Current event", C.inf], [`Selected analogue (${ANALOGUES[sel][2].slice(-4)})`, "#cfe3fb"], ["Other analogues", "#51688c"]].map(([l, c], i) => <g key={l}><rect x={826} y={30 + i * 19} width={12} height={3} fill={c} /><text x={844} y={34 + i * 19} className="an">{l}</text></g>)}
            </Chart>
          </Card>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
            {[["3 – 7 days", "typical duration of similar events (median 4.5)"], ["4 of 5", "expanded further after day 2"], ["Day 3 – 4", "when fire power usually began to decay"]].map(([v, l]) => <Card key={v}><p className="big" style={{ fontSize: 22 }}>{v}</p><p className="note" style={{ fontSize: 10.5 }}>{l}</p></Card>)}
            <Card accent={C.inf}><b style={{ color: C.inf, fontSize: 11.5 }}>Context, not a prediction</b><p className="note" style={{ fontSize: 11 }}>The current fire may behave differently from its analogues.</p></Card>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- 06 · Fire Future: forecast corridor -------------------------------------------------------

const HORIZON: Record<string, { bands: number; scale: number; area: string; high: string }> = {
  "Next 6 h": { bands: 1, scale: 0.7, area: "3.1 km²", high: "1.9 km²" },
  "Next 12 h": { bands: 2, scale: 0.85, area: "12.4 km²", high: "4.6 km²" },
  "Next 24 h": { bands: 3, scale: 1, area: "41 km²", high: "9.8 km²" },
};
const MODELS: Array<[string, string, string, string, string]> = [["Persistence baseline", "0.58", "0.41", "0.162", "0.31"], ["Seasonal baseline", "0.44", "0.55", "0.189", "0.22"], ["Wind-only baseline", "0.61", "0.39", "0.151", "0.34"], ["LightGBM ✓ in use", "0.72", "0.29", "0.118", "0.46"]];
const INPUTS = ["Recent event behaviour", "Historical fire patterns", "Similar past events", "Wind · SW 12 km/h", "Humidity · 48%", "Season", "Terrain", "Land cover", "Recent satellite observations"];

export function FireFuture() {
  const [h, setH] = useState("Next 24 h");
  const hz = HORIZON[h];
  return (
    <div className="stage">
      <LocalMap className="bg" viewBox="-260 -10 1500 800">
        <Corridor bands={hz.bands} scale={hz.scale} />
        <EventDot />
        <defs><marker id="wind" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={7} markerHeight={7} orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#fff" /></marker></defs>
        <line x1={318} y1={500} x2={356} y2={456} stroke="#fff" strokeWidth={1.6} markerEnd="url(#wind)" />
        <text x={300} y={520} className="map-label">wind · SW 12 km/h</text>
      </LocalMap>

      <div className="dock l" style={{ width: 326 }}>
        <Card glass>
          <p className="eyebrow" style={{ margin: 0 }}>06 · Fire Future</p>
          <h3>Where might new activity be detected?</h3>
          <Seg options={Object.keys(HORIZON)} value={h} onChange={setH} />
          <p className="note">Areas where new <b style={{ color: "var(--text)" }}>satellite-observed</b> burning activity may appear in the next valid observation windows.</p>
          <p className="fine">Not a prediction of physical fire spread. The fire will not “definitely reach” any location.</p>
        </Card>
        <Card glass title="Next valid observations">
          <div><KV k="VIIRS · NOAA-21" v="22 Mar 19:41 UTC" /><KV k="VIIRS · Suomi NPP" v="22 Mar 20:06 UTC" /><KV k="VIIRS · NOAA-20" v="22 Mar 20:31 UTC" /><KV k="MODIS · Terra" v="23 Mar 03:58 UTC" /></div>
        </Card>
        <Card glass title="Inputs used" className="grow">
          <div className="row wrap" style={{ gap: 5 }}>{INPUTS.map((s, i) => <Chip key={s} sm tone={i === 0 ? C.inf : undefined}>{s}</Chip>)}</div>
          <p className="card-h" style={{ marginTop: 6 }}>Model in use</p>
          <div><b>LightGBM · v0.4</b><p className="note" style={{ fontSize: 10.5 }}>Used because it beats all baselines on held-out years and regions.</p></div>
        </Card>
      </div>

      <div className="dock r" style={{ width: 452 }}>
        <Card glass title="Does the model beat simple baselines?">
          <table className="tbl">
            <thead><tr><th>Method</th><th className="n">Detection</th><th className="n">False alarms</th><th className="n">Calibration</th><th className="n">Footprint</th></tr></thead>
            <tbody>{MODELS.map(([m, ...v], i) => <tr key={m} className={i === 3 ? "hl" : ""}><td style={i === 3 ? { fontWeight: 700 } : undefined}>{m}</td>{v.map((n, j) => <td key={j} className="n">{n}</td>)}</tr>)}</tbody>
          </table>
          <p className="note" style={{ fontSize: 10 }}>Detection = share of new detections inside the corridor · False alarms = corridor area with no new detection · Calibration = Brier score (lower is better) · Footprint = overlap with observed activity (IoU)</p>
          <div className="row wrap"><Chip sm>Temporal holdout · 2023–2025</Chip><Chip sm>Spatial holdout · unseen regions</Chip></div>
        </Card>
        <Card glass title={`Corridor for this event · ${h.replace("Next ", "")}`}>
          <div><KV k="Most likely direction" v="north-east" /><KV k="High-likelihood area (≥ 60%)" v={hz.high} /><KV k="Full corridor (≥ 15%)" v={hz.area} /><KV k="Nearest forest edge" v="≈ 14 km east · outer band only" /></div>
        </Card>
        <Card glass title="When the system holds back" className="grow">
          <div className="inner" style={{ borderColor: "rgba(167,139,250,0.45)", background: "rgba(167,139,250,0.07)" }}>
            <p className="mono" style={{ fontWeight: 700, letterSpacing: "0.14em" }}>FORECAST WITHHELD</p>
            <p style={{ fontSize: 11.5, margin: "4px 0" }}>Event FS-BD-2026-0397 · Rangamati Hill District</p>
            <p className="note" style={{ fontSize: 10.5 }}>Cloud on the last 3 passes · observation sufficiency 0.18. Too little recent evidence for a reliable corridor.</p>
          </div>
        </Card>
      </div>

      <Card glass className="float" title={`Likelihood of a new detection · ${h.toLowerCase()}`} style={{ left: 358, bottom: 14, padding: "9px 12px", gap: 6 }}>
        <Legend items={[["≥ 60%", "#8b5cf6"], ["35 – 60%", "rgba(167,139,250,0.5)"], ["15 – 35%", "rgba(167,139,250,0.25)"], ["Forest outline (approx.)", "#1f4a45"]]} />
      </Card>
    </div>
  );
}

// --- 07 · Exposure -----------------------------------------------------------------------------

const ASSET_LAYERS: Array<[string, string, string, string]> = [
  ["P", "Population", "0 · 3,400", "#f2c94c"], ["V", "Villages", "0 · 3", "#e8eef8"], ["R", "Roads", "0 · 6 km", "#9aa7bb"], ["A", "Agricultural areas", "0 · 4.2 km²", "#a3d65c"], ["F", "Forests", "41 km²", "#3ecf8e"],
  ["S", "Protected areas", "1", "#34d399"], ["E", "Schools", "0 · 1", "#5aa2e6"], ["H", "Hospitals & clinics", "0 · 0", "#ef5350"], ["W", "Power infrastructure", "0 · 5 km", "#f28b3c"], ["C", "Critical facilities", "2 · 0", "#c4b5fd"],
];
const SUMMARY: Array<[string, string, string, string]> = [
  ["Population", "0", "≈ 3,400", "3 villages across the river"], ["Villages", "0", "3", "east bank, outside the forest"], ["Roads", "0 km", "6 km", "local road"], ["Agricultural areas", "0", "4.2 km²", "rice and fallow fields"],
  ["Forests", "41 km²", "–", "mangrove forest"], ["Protected areas", "1", "–", "Sundarbans East Wildlife Sanctuary"], ["Schools", "0", "1", "primary school"], ["Hospitals & clinics", "0", "0", "nearest 21 km"],
  ["Power infrastructure", "0", "5 km", "11 kV distribution line"], ["Critical facilities", "2", "0", "forest camps; staff, fishers and honey collectors may be present"],
];
const MARKERS: Array<[string, string, number, number, string]> = [
  ["C", "forest camp", 520, 318, "#c4b5fd"], ["C", "forest camp", 468, 368, "#c4b5fd"], ["V", "village", 724, 192, "#e8eef8"], ["V", "village", 748, 254, "#e8eef8"], ["V", "village", 716, 326, "#e8eef8"],
  ["A", "farmland", 796, 218, "#a3d65c"], ["A", "farmland", 790, 352, "#a3d65c"], ["E", "school", 760, 300, "#5aa2e6"],
];

export function Exposure() {
  const [h, setH] = useState("24 h corridor");
  const [off, setOff] = useState<string[]>([]);
  const shape = h === "6 h" ? { bands: 1, scale: 0.7 } : h === "12 h" ? { bands: 2, scale: 0.85 } : { bands: 3, scale: 1 };
  return (
    <div className="stage">
      <LocalMap className="bg" viewBox="-90 20 1420 760">
        <text x={330} y={620} textAnchor="middle" className="map-caps">SUNDARBANS EAST WILDLIFE SANCTUARY</text>
        <Corridor {...shape} labels={h === "24 h corridor"} />
        <EventDot r={30} />
        {!off.includes("W") && <g><line x1={705} y1={130} x2={698} y2={420} stroke="#f28b3c" strokeDasharray="4 3" strokeWidth={1.4} /><text x={708} y={128} className="map-label">11 kV line</text></g>}
        {!off.includes("R") && <g><path d="M724,140 C730,240 722,330 728,430" fill="none" stroke="#9aa7bb" strokeWidth={1.6} /><text x={736} y={432} className="map-label">local road</text></g>}
        {MARKERS.filter(([k]) => !off.includes(k)).map(([k, label, x, y, color], i) => (
          <g key={i}><rect x={x - 7} y={y - 7} width={14} height={14} rx={3} fill={color} /><text x={x} y={y + 3.2} textAnchor="middle" style={{ fontSize: 8.5, fontWeight: 700, fill: "#0b1220" }}>{k}</text><text x={x + 12} y={y + 3.5} className="map-label">{label}</text></g>
        ))}
      </LocalMap>

      <div className="dock l" style={{ width: 296 }}>
        <Card glass>
          <p className="eyebrow" style={{ margin: 0 }}>07 · Exposure</p>
          <h3>What lies in the activity corridor?</h3>
          <Seg options={["6 h", "12 h", "24 h corridor"]} value={h} onChange={setH} />
        </Card>
        <Card glass title="Layers" meta="in · near corridor" className="grow">
          <div className="col" style={{ gap: 10 }}>
            {ASSET_LAYERS.map(([k, name, v, color]) => (
              <button key={k} type="button" className="row" style={{ background: "none", border: 0, padding: 0, fontSize: 11.5, opacity: off.includes(k) ? 0.35 : 1 }} onClick={() => setOff(off.includes(k) ? off.filter((o) => o !== k) : [...off, k])}>
                <i style={{ width: 16, height: 16, borderRadius: 4, background: color, color: "#0b1220", fontStyle: "normal", fontWeight: 700, fontSize: 9, display: "grid", placeItems: "center", flex: "none" } as CSSProperties}>{k}</i>
                <span style={{ color: "var(--soft)" }}>{name}</span><span className="mono right" style={{ fontSize: 9.5, color: "var(--dim)" }}>{v}</span>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div className="dock r" style={{ width: 440 }}>
        <Card glass accent={C.fc} title={`Exposure summary · ${EVENT.id} · next ${h.replace(" corridor", "")}`} className="grow">
          <table className="tbl">
            <thead><tr><th>Asset</th><th className="n">Inside corridor</th><th className="n">Within 3 km</th><th>Note</th></tr></thead>
            <tbody>{SUMMARY.map(([a, inside, near, note]) => <tr key={a}><td>{a}</td><td className="n">{inside}</td><td className="n">{near}</td><td style={{ color: "var(--muted)", fontSize: 10.5 }}>{note}</td></tr>)}</tbody>
          </table>
          <div className="inner" style={{ borderColor: "rgba(167,139,250,0.4)", background: "rgba(167,139,250,0.06)" }}>
            <p style={{ fontSize: 11.5 }}>These assets lie <b>inside or near the possible future activity corridor</b>. This does not mean they will be affected.</p>
          </div>
          <p className="fine">Population from gridded census estimates · assets from OpenStreetMap · positions on this map are schematic.</p>
        </Card>
      </div>
    </div>
  );
}

export { EVT };
