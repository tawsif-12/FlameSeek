import { useMemo } from "react";
import type { CSSProperties } from "react";
import { EVENT, rng } from "../data";
import { EVT, LocalMap } from "../maps";
import { C, Card, Chart, Chip, KV, PageHead, YGrid, lin, smooth } from "../ui";

const DAYS: Array<[string, string]> = [["Day 1 · 20 Mar", "#f2c94c"], ["Day 2 · 21 Mar", "#f28b3c"], ["Day 3 · 22 Mar", "#ef5350"]];
const DETECTIONS: Array<[string, string, boolean, string, string, string]> = [
  ["22 Mar 07:52", "VIIRS NOAA-20", true, "96.4", "high", "Day"], ["22 Mar 07:27", "VIIRS Suomi NPP", true, "88.1", "high", "Day"], ["22 Mar 07:02", "VIIRS NOAA-21", true, "71.9", "high", "Day"],
  ["22 Mar 04:12", "MODIS Terra", false, "64", "92%", "Day"], ["21 Mar 19:44", "VIIRS NOAA-21", true, "41.3", "nominal", "Night"], ["21 Mar 15:58", "MODIS Terra", false, "28.6", "81%", "Night"],
  ["21 Mar 07:31", "VIIRS Suomi NPP", true, "36.7", "nominal", "Day"], ["20 Mar 07:41", "VIIRS NOAA-21", true, "12.2", "nominal", "Day"],
];
const PASSES: Array<[number, number]> = [[12, 0], [8, 0], [14, 0], [22, 1], [36, 1], [28, 1], [41, 2], [64, 2], [96, 2]];
const STATES = ["Onset", "Intensifying", "Expanding", "Persistent", "Stable", "Decaying", "Uncertain"];

export default function FireIdentity() {
  const pixels = useMemo(() => {
    const r = rng(63);
    const centres: Array<[number, number, number, number]> = [[265, 318, 46, 16], [330, 262, 62, 22], [420, 198, 70, 25]];
    return centres.flatMap(([cx, cy, spread, n], day) =>
      Array.from({ length: n }, () => ({ x: cx + (r() - 0.5) * spread * 1.7 + (r() - 0.5) * 20, y: cy + (r() - 0.5) * spread, day, modis: r() > 0.72 })),
    );
  }, []);
  const hull = (day: number, pad: number) => {
    const p = pixels.filter((q) => q.day <= day);
    const xs = p.map((q) => q.x), ys = p.map((q) => q.y);
    const [x0, x1, y0, y1] = [Math.min(...xs) - pad, Math.max(...xs) + pad, Math.min(...ys) - pad, Math.max(...ys) + pad];
    return `${x0},${y1} ${x0 + (x1 - x0) * 0.15},${y0 + (y1 - y0) * 0.45} ${x0 + (x1 - x0) * 0.62},${y0} ${x1},${y0 + (y1 - y0) * 0.1} ${x1},${y0 + (y1 - y0) * 0.5} ${x0 + (x1 - x0) * 0.55},${y1}`;
  };
  const by = lin(0, 100, 118, 12);
  const ty = lin(0, 100, 62, 8);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="03 · Fire Identity"
        title="63 detections, one evolving fire event"
        sub="Detections from different satellites, passes and days are grouped into a single fire event by spatial-temporal clustering and event association."
        right={<><Chip tone={C.obs}>63 raw detections</Chip><Chip tone={C.inf}>→ 1 reconstructed event</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1fr 1.45fr 0.95fr" }}>
        <div className="col">
          <Card title="Where the event is" meta={EVENT.place} className="grow">
            <div className="grow" style={{ position: "relative", minHeight: 200, borderRadius: 8, overflow: "hidden" }}>
              <LocalMap viewBox="150 60 600 480" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
                <g><circle cx={250} cy={92} r={2.2} fill="#dbe5f5" /><text x={257} y={95.5} className="map-label">Mongla</text></g>
                <g><circle cx={520} cy={150} r={2.2} fill="#dbe5f5" /><text x={527} y={153.5} className="map-label">Morrelganj</text></g>
                <circle cx={EVT[0]} cy={EVT[1] - 60} r={15} fill="rgba(239,83,80,0.7)" stroke="#fda4a4" />
                <text x={EVT[0] + 21} y={EVT[1] - 56} className="map-label">{EVENT.id}</text>
              </LocalMap>
            </div>
          </Card>
          <Card title="Linked satellite detections" meta="8 of 63">
            <table className="tbl">
              <thead><tr><th>UTC</th><th>Sensor</th><th className="n">FRP MW</th><th className="n">Conf.</th><th>Day/night</th></tr></thead>
              <tbody>
                {DETECTIONS.map(([t, s, viirs, frp, conf, dn]) => (
                  <tr key={t}><td className="mono" style={{ fontSize: 10.5 }}>{t}</td><td><i style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: viirs ? "#ef5350" : "#f2c94c", marginRight: 6 }} />{s}</td><td className="n">{frp}</td><td className="n">{conf}</td><td style={{ color: "var(--muted)" }}>{dn}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>

        <div className="col">
          <Card title="Event reconstruction on the 1 km grid" meta="outline = event extent at end of each day" className="grow">
            <Chart w={640} h={400}>
              {Array.from({ length: 17 }, (_, i) => <line key={`v${i}`} x1={40 + i * 36} x2={40 + i * 36} y1={20} y2={380} stroke="#162238" />)}
              {Array.from({ length: 11 }, (_, i) => <line key={`h${i}`} x1={40} x2={616} y1={20 + i * 36} y2={20 + i * 36} stroke="#162238" />)}
              {[2, 1, 0].map((d) => <polygon key={d} points={hull(d, 16)} fill={`${DAYS[d][1]}14`} stroke={DAYS[d][1]} strokeWidth={1.2} strokeLinejoin="round" />)}
              {pixels.map((p, i) => p.modis
                ? <rect key={i} x={p.x - 15} y={p.y - 15} width={30} height={30} fill="none" stroke={DAYS[p.day][1]} strokeWidth={1.2} />
                : <rect key={i} x={p.x - 5} y={p.y - 5} width={10} height={10} fill={DAYS[p.day][1]} />)}
              <defs><marker id="arr" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={7} markerHeight={7} orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#fff" /></marker></defs>
              <path d="M262,322 Q330,300 432,196" fill="none" stroke="#fff" strokeWidth={2} markerEnd="url(#arr)" />
              {DAYS.map(([label, color], i) => <g key={label}><rect x={498} y={30 + i * 19} width={9} height={9} fill={color} /><text x={513} y={38.5 + i * 19} className="an">{label}</text></g>)}
              <rect x={498} y={92} width={9} height={9} fill="none" stroke="#dbe5f5" /><text x={513} y={100.5} className="an">MODIS 1 km</text>
              <rect x={500} y={113} width={5} height={5} fill="#dbe5f5" /><text x={513} y={119.500} className="an">VIIRS 375 m</text>
              <text x={42} y={395} className="ax">grid 1 km · view ≈ 16 × 10 km</text>
            </Chart>
          </Card>
          <Card title="Inferred fire behaviour state" meta="per overpass">
            <svg viewBox="0 0 640 138" style={{ width: "100%", height: 138, flex: "none" }}>
              <YGrid ticks={[0, 50, 100]} y={by} x0={40} x1={620} />
              {[["Onset", 46, 190, "#5b7393"], ["Intensifying", 240, 190, "#d9b13b"], ["Expanding", 434, 186, C.inf]].map(([l, x, w, c]) => (
                <g key={l as string}><rect x={x as number} y={0} width={w as number} height={15} rx={3} fill={`color-mix(in srgb, ${c} 28%, #0e1626)`} stroke={c as string} strokeWidth={0.8} /><text x={(x as number) + (w as number) / 2} y={10.5} textAnchor="middle" className="an" style={{ fill: "#fff", fontWeight: 700 }}>{l}</text></g>
              ))}
              {PASSES.map(([frp, day], i) => <rect key={i} x={52 + i * 63} y={by(frp)} width={44} height={118 - by(frp)} fill={i % 2 ? "#f2c94c" : "#ef5350"} opacity={0.75 + day * 0.12} />)}
              <text x={40} y={132} className="ax">20 Mar</text><text x={620} y={132} textAnchor="end" className="ax">22 Mar 07:52 · FRP (MW) per overpass</text>
            </svg>
            <div className="row wrap">{STATES.map((s) => <Chip key={s} sm tone={s === "Expanding" ? C.inf : undefined}>{s === "Expanding" ? <b style={{ color: "#fff" }}>{s}</b> : <span style={{ opacity: STATES.indexOf(s) < 3 ? 1 : 0.5 }}>{s}</span>}</Chip>)}</div>
          </Card>
        </div>

        <Card accent={C.inf} title="Fire event" meta={<Chip sm tone={C.inf}>Expanding</Chip>}>
          <div><p className="mono" style={{ fontSize: 17, fontWeight: 700 }}>{EVENT.id}</p><p className="note" style={{ fontSize: 10.5 }}>{EVENT.range}</p></div>
          <div>
            <KV k="First detection" v="20 Mar 2026 · 07:41 UTC" />
            <KV k="Latest detection" v="22 Mar 2026 · 07:52 UTC" />
            <KV k="Event duration" v="2 d 0 h (still active)" />
            <KV k="Observations" v="63 detections · 9 passes" />
            <KV k="Sensors involved" v="Terra · Aqua · SNPP · N20 · N21" />
            <KV k="Geographic spread" v="4.8 → 12.6 km² (24 h)" />
            <KV k="Movement" v="north-east · ≈ 2.1 km/day" />
            <KV k="Association confidence" v="0.91" />
          </div>
          <p className="card-h">Fire power trend</p>
          <svg viewBox="0 0 400 70" style={{ width: "100%", height: 70, flex: "none" }}>
            <path d={`${smooth(PASSES.map(([f], i) => [8 + i * 47, ty(f)]))} L384,66 L8,66 Z`} fill="rgba(242,139,60,0.14)" />
            <path d={smooth(PASSES.map(([f], i) => [8 + i * 47, ty(f)]))} fill="none" stroke={C.inf} strokeWidth={2} />
            <circle cx={384} cy={ty(96)} r={3.5} fill={C.inf} /><text x={376} y={ty(96) - 5} textAnchor="end" className="ax">96 MW</text>
          </svg>
          <div className="inner" style={{ "--c": C.inf } as CSSProperties}>
            <p style={{ fontSize: 11.5 }}><b>Why “Expanding”:</b> spatial extent grew 162% in 24 h while fire power rose and detections persisted across 3 consecutive days.</p>
            <p className="fine" style={{ marginTop: 5 }}>An inferred behaviour state, not a direct measurement of physical fire spread.</p>
          </div>
          <p className="card-h">Method</p>
          <div className="row wrap"><Chip sm>space-time clustering · 2 km / 18 h</Chip><Chip sm>event association</Chip><Chip sm>cross-sensor matching</Chip></div>
        </Card>
      </div>
    </div>
  );
}
