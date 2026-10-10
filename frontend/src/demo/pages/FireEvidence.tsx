import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { EVENT, rng } from "../data";
import { Corridor, EVT, LocalMap } from "../maps";
import { Bar, C, Card, Chart, Chip, KV, PageHead, lin } from "../ui";

// --- 04 · Fire Evidence: independent sources ---------------------------------------------------

const SATS: Array<[string, string, string, string, string]> = [
  ["Sentinel-2 · MSI", "21 Mar 04:35 UTC", "Smoke plume and active fire line visible · burn scar ≈ 3.1 km²", "supports", C.ext],
  ["Landsat 9 · OLI / TIRS", "", "No acquisition since first detection", "next pass 24 Mar", ""],
  ["Copernicus · EMS", "", "No rapid-mapping activation for this area", "no activation", ""],
];
const OFFICIAL: Array<[string, string, string, string]> = [
  ["Forest department · Sundarbans East Division", "Searched notices and press releases · last 48 h", "no report yet", C.yellow],
  ["Fire service & civil defence", "Forest fires usually reported by the forest department", "no report", ""],
  ["Disaster management authority", "No situation report for Bagerhat", "no report", ""],
  ["Meteorological agency", "Dry spell · humidity 48% · south-west wind 12 km/h", "context", C.ext],
  ["Environment ministry · civil protection", "No public statements found", "no report", ""],
];
const GEO: Array<[string, number, string]> = [["Himawari-9 pixel · 0 km", 0, C.ext], ["Sentinel-2 fire line · 0.4 km", 0.4, C.ext], ["News report A · 3.2 km", 3.2, C.obs], ["News report B · 4.1 km", 4.1, C.obs], ["Met. bulletin (district) · 12 km", 12, "#b4c0d4"]];
const TIME: Array<[string, number, string]> = [["Himawari-9 first anomaly · −21 min", -0.35, C.ext], ["News report A published · +4 h 20 min", 4.3, C.obs], ["Sentinel-2 image · +20 h", 20, C.ext], ["News report B published · +26 h", 26, C.obs]];

export function EvidenceSources() {
  const scans = useMemo(() => {
    const r = rng(9);
    return Array.from({ length: 150 }, (_, i) => (i < 16 ? 0 : r() > 0.26 ? 1 : r() > 0.5 ? 2 : 0));
  }, []);
  const gx = lin(0, 30, 30, 700);
  const tx = lin(-12, 48, 30, 700);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="04 · Fire Evidence · independent sources"
        title="Do other satellites and official sources support it?"
        sub={`${EVENT.id} · first detected 20 Mar 2026, 07:41 UTC. Each source is matched to the event in space and in time.`}
        right={<><Chip tone={C.ext}>5 sources checked</Chip><Chip tone={C.ext}>3 support the event</Chip><Chip tone={C.obs}>1 pending</Chip></>}
      />
      <div className="grid" style={{ gridTemplateColumns: "0.85fr 1.5fr 1.05fr" }}>
        <Card accent={C.obs} title="Where exactly · reverse geocoding">
          <div style={{ position: "relative", height: 122, borderRadius: 8, overflow: "hidden", flex: "none" }}>
            <LocalMap viewBox="180 140 560 360" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}><circle cx={EVT[0]} cy={EVT[1] - 70} r={12} fill="rgba(239,83,80,0.75)" stroke="#fda4a4" /></LocalMap>
          </div>
          <div>
            <KV k="Country" v="Bangladesh" /><KV k="Division" v="Khulna" /><KV k="District" v="Bagerhat" /><KV k="Upazila" v="Sharankhola" />
            <KV k="Nearest settlement" v="Rayenda · 21 km N" /><KV k="Forest / protected area" v="Sundarbans Reserve Forest · East Wildlife Sanctuary" /><KV k="Coordinates" v="22.121° N, 89.803° E (± 0.4 km)" />
          </div>
        </Card>
        <Card accent={C.ext} title="Regional satellite verification" meta="chosen for Asia-Pacific">
          <div className="row"><b>Himawari-9 · AHI</b><span className="note" style={{ fontSize: 10.5 }}>geostationary · every 10 minutes</span><span className="right"><Chip sm tone={C.ext}>supports</Chip></span></div>
          <svg viewBox="0 0 750 74" preserveAspectRatio="none" style={{ width: "100%", height: 74, flex: "none" }}>
            <line x1={0} x2={750} y1={56} y2={56} stroke="#26364f" strokeDasharray="2 3" />
            {scans.map((s, i) => s === 1 ? <rect key={i} x={i * 5} y={14} width={3.6} height={42} fill={C.ext} /> : s === 2 ? <rect key={i} x={i * 5} y={38} width={3.6} height={18} fill="#3a4a66" /> : null)}
            <line x1={80} x2={80} y1={4} y2={58} stroke={C.inf} strokeWidth={1.5} />
          </svg>
          <div className="row mono" style={{ justifyContent: "space-between", fontSize: 8.5, color: "var(--dim)", marginTop: -8 }}><span>20 Mar 00:00 · first anomaly ▲</span><span>21 Mar 00:00</span><span>22 Mar 00:00</span><span><i style={{ color: C.ext }}>■</i> anomaly &nbsp;<i style={{ color: "#3a4a66" }}>■</i> cloud</span></div>
          <p className="note" style={{ fontSize: 10.5 }}>Thermal anomaly in 214 of 288 clear scans since first detection · first seen 07:20 UTC, 21 min before VIIRS</p>
          <div>
            {SATS.map(([name, when, detail, state, tone]) => (
              <div key={name} className="kv" style={{ alignItems: "center", padding: "8px 0" }}>
                <span style={{ whiteSpace: "normal" }}><b style={{ color: "var(--text)", fontFamily: "var(--body)", fontSize: 12 }}>{name}</b> <i className="mono" style={{ fontStyle: "normal", fontSize: 9, color: "var(--dim)" }}>{when}</i><br /><small style={{ fontSize: 10.5 }}>{detail}</small></span>
                <Chip sm tone={tone || undefined}>{state}</Chip>
              </div>
            ))}
          </div>
        </Card>
        <Card accent={C.ext} title="Government & official sources" meta="checked 14:40 UTC">
          <div>
            {OFFICIAL.map(([name, detail, state, tone]) => (
              <div key={name} className="kv" style={{ alignItems: "center", padding: "8px 0" }}>
                <span style={{ whiteSpace: "normal" }}><b style={{ color: "var(--text)", fontFamily: "var(--body)", fontSize: 12 }}>{name}</b><br /><small style={{ fontSize: 10.5 }}>{detail}</small></span>
                <Chip sm tone={tone || undefined}>{state}</Chip>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <div className="grid fill" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Card title="Geographic matching" meta="distance from the fire event">
          <Chart w={740} h={210}>
            <rect x={gx(0)} y={24} width={gx(5) - gx(0)} height={150} fill="rgba(62,207,142,0.12)" /><rect x={gx(5)} y={24} width={gx(15) - gx(5)} height={150} fill="rgba(242,201,76,0.07)" /><rect x={gx(15)} y={24} width={gx(30) - gx(15)} height={150} fill="rgba(239,83,80,0.07)" />
            {[["strong ≤ 5 km", 0], ["moderate", 5], ["weak", 15]].map(([l, v]) => <text key={l} x={gx(v as number) + 5} y={17} className="ax">{l}</text>)}
            {GEO.map(([label, km, color], i) => <g key={label}><line x1={gx(0)} x2={gx(km)} y1={42 + i * 25} y2={42 + i * 25} stroke="#3a4a66" /><circle cx={gx(km)} cy={42 + i * 25} r={4.5} fill={color} /><text x={gx(km) + 10} y={45.5 + i * 25} className="an">{label}</text></g>)}
            <text x={gx(30) - 4} y={168} textAnchor="end" className="an" style={{ fill: "#ef9a9a" }}>Building fire report, Gazipur · 214 km → rejected ▸</text>
            {[0, 5, 10, 15, 20, 25, 30].map((v) => <text key={v} x={gx(v)} y={192} textAnchor="middle" className="ax">{v} km</text>)}
          </Chart>
        </Card>
        <Card title="Temporal matching" meta="time relative to first satellite detection">
          <Chart w={740} h={210}>
            <rect x={tx(-2)} y={24} width={tx(12) - tx(-2)} height={150} fill="rgba(62,207,142,0.12)" /><text x={tx(-2)} y={17} className="ax">strong match window</text>
            <line x1={tx(0)} x2={tx(0)} y1={24} y2={176} stroke={C.inf} strokeWidth={1.6} />
            {TIME.map(([label, h, color], i) => <g key={label}><circle cx={tx(h)} cy={42 + i * 27} r={4.5} fill={color} /><text x={tx(h) + 10} y={45.5 + i * 27} className="an">{label}</text></g>)}
            <text x={tx(-11)} y={152} className="an" style={{ fill: "#8a96aa" }}>◂ Forest fire article from 5 days earlier → low relevance</text>
            <text x={tx(0) + 6} y={170} className="ax" style={{ fill: "var(--inf)" }}>VIIRS first detection · 20 Mar 07:41</text>
            {[-12, 0, 12, 24, 36, 48].map((v) => <text key={v} x={tx(v)} y={192} textAnchor="middle" className="ax">{v > 0 ? `+${v}` : v} h</text>)}
          </Chart>
        </Card>
      </div>
    </div>
  );
}

// --- Fire Evidence · local news & NLP ----------------------------------------------------------

type Article = { source: string; when: string; title: string; kind: string; summary: string; chips: Array<[string, string?]>; relevance: string };
const ARTICLES: Article[] = [
  { source: "Local English daily", when: "20 Mar · 18:02 local", title: "Fire breaks out in Sharankhola range of East Sundarbans", kind: "AI-generated summary", summary: "A fire started in the Sharankhola range on Friday afternoon. Forest staff suspect an unattended fire at a fishing camp; about 3 hectares affected.", chips: [["3.2 km away"], ["+4 h 20 min"], ["Forest fire", C.inf]], relevance: "0.93" },
  { source: "National news portal", when: "21 Mar · 14:10 local", title: "Sundarbans fire still burning, firefighters lay pipes from canal", kind: "AI-generated summary", summary: "The fire continued into a second day. Teams brought water from a nearby canal; smoke visible from villages at the forest edge.", chips: [["4.1 km away"], ["+26 h"], ["Forest fire", C.inf]], relevance: "0.88" },
  { source: "Video post · local resident", when: "20 Mar · 15:40 local", title: "42-second clip: smoke over the forest edge near Sharankhola", kind: "Read from caption + speech-to-text", summary: "“Fire in the Sundarbans since this afternoon, near the Dhanshagor camp.” Place and time extracted from the text, not the image.", chips: [["≈ 5 km"], ["+2 h"], ["first posted today", C.ext]], relevance: "0.71" },
];
const CLASSES: Array<[string, number]> = [["Forest fire", 81], ["Wildfire", 9], ["Land clearing", 3], ["Controlled burn", 2], ["Agricultural burn", 2], ["Deforestation-related burning", 1], ["Building fire", 0.6], ["Factory fire", 0.4], ["Industrial heat source", 0.3], ["Gas flare", 0.2], ["Volcanic activity", 0], ["Unknown thermal event", 1]];
const PIPELINE = ["Collect country news & posts", "Speech-to-text for videos", "Entity extraction", "Event classification", "Geocode place names", "Match in space & time"];
const Hl = ({ c, tag, children }: { c: string; tag: string; children: ReactNode }) => <span className="hl" style={{ "--c": c } as CSSProperties}>{children}<sup>{tag}</sup></span>;

export function EvidenceNews() {
  const [sel, setSel] = useState(0);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="04 · Fire Evidence · local news & NLP"
        title="What are people on the ground reporting?"
        sub="English-language news from Bangladesh is read by an NLP model that extracts place, time and event type, then matched to the fire event."
        right={<><Chip tone={C.ext}>12 reports & posts</Chip><Chip tone={C.ext}>3 matched</Chip><Chip tone={C.red}>9 rejected</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1fr 1.35fr" }}>
        <div className="col">
          {ARTICLES.map((a, i) => (
            <Card key={a.title} accent={C.ext} style={{ cursor: "pointer", gap: 7, outline: i === sel ? "1px solid rgba(62,207,142,0.5)" : "none" }}>
              <div className="row" onClick={() => setSel(i)}><Chip sm tone={C.ext}>ORIGINAL SOURCE</Chip><b style={{ fontSize: 11 }}>{a.source}</b><span className="mono right" style={{ fontSize: 9, color: "var(--dim)" }}>{a.when} · link ↗</span></div>
              <b style={{ fontSize: 12.5 }} onClick={() => setSel(i)}>{a.title}</b>
              <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }} onClick={() => setSel(i)}>
                <div className="inner"><p className="card-h" style={{ fontSize: 8, color: "var(--dim)" }}>{a.kind}</p><p className="note" style={{ fontSize: 10.5, marginTop: 4 }}>{a.summary}</p></div>
                <div className="inner" style={{ borderColor: "rgba(242,139,60,0.35)" }}><p className="card-h" style={{ fontSize: 8, color: C.inf }}>System interpretation</p><div className="row wrap" style={{ marginTop: 6, gap: 5 }}>{a.chips.map(([t, tone]) => <Chip key={t} sm tone={tone}>{t}</Chip>)}<Chip sm tone={C.ext}>relevance {a.relevance}</Chip></div></div>
              </div>
            </Card>
          ))}
          <Card accent={C.red} style={{ gap: 7 }}>
            <div className="row"><Chip sm tone={C.red}>REJECTED</Chip><b style={{ fontSize: 11 }}>National daily</b><span className="mono right" style={{ fontSize: 9, color: "var(--dim)" }}>21 Mar · 09:30 local</span></div>
            <b style={{ fontSize: 12.5 }}>Fire at garment warehouse in Gazipur, no casualties</b>
            <div className="row wrap" style={{ gap: 5 }}><Chip sm>214 km away</Chip><Chip sm>+19 h</Chip><Chip sm>Building fire</Chip><Chip sm tone={C.red}>relevance 0.04</Chip><span className="note" style={{ fontSize: 10.5 }}>The word “fire” alone is not confirmation.</span></div>
          </Card>
        </div>
        <Card title={`NLP event extraction · article ${"ABC"[sel]}`} meta="entities · classification">
          <p className="article">
            A <Hl c={C.red} tag="EVENT">fire broke out</Hl> on <Hl c={C.fc} tag="DATE · TIME">Friday afternoon</Hl> inside the <Hl c={C.obs} tag="LOCATION">Sharankhola range of the East Sundarbans</Hl>, near the{" "}
            <Hl c={C.inf} tag="INFRASTRUCTURE">Dhanshagor forest camp</Hl>, forest officials said. The blaze, believed to have started from an <Hl c={C.yellow} tag="CAUSE">unattended fire at a fishing camp</Hl>,{" "}
            <Hl c={C.inf} tag="IMPACT">spread through dry undergrowth</Hl> and has affected <Hl c={C.ext} tag="AFFECTED AREA">about 3 hectares of forest</Hl>.
          </p>
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[["Location", "Sharankhola, East Sundarbans"], ["Date · time", "20 Mar 2026 · afternoon"], ["Event type", "Forest fire"], ["Cause", "Unattended camp fire (suspected)"], ["Impact", "Spread through undergrowth"], ["Infrastructure", "Forest camp"], ["Affected area", "≈ 3 ha"], ["Geocoded to", "22.14 N, 89.78 E"]].map(([k, v]) => (
              <div key={k} className="inner" style={{ padding: "7px 10px" }}><p className="card-h" style={{ fontSize: 7.5, color: "var(--dim)" }}>{k}</p><p style={{ fontSize: 11.5, marginTop: 3 }}>{v}</p></div>
            ))}
          </div>
          <p className="card-h">NLP pipeline</p>
          <div className="row wrap" style={{ gap: 5 }}>{PIPELINE.map((s, i) => <span key={s} className="row" style={{ gap: 5 }}><Chip sm tone={i === 5 ? C.ext : undefined}>{s}</Chip>{i < 5 && <span style={{ color: "var(--dim)" }}>→</span>}</span>)}</div>
          <p className="card-h">Event classification</p>
          <div className="col grow" style={{ gap: 0, justifyContent: "space-between" }}>
            {CLASSES.map(([label, pct], i) => (
              <div key={label} className="row" style={{ fontSize: 11, padding: "3px 0" }}><span style={{ width: 190, color: i ? "var(--muted)" : "var(--text)", fontWeight: i ? 400 : 700 }}>{label}</span><Bar value={pct / 100} color={i ? "#3b5c8f" : C.inf} /><span className="mono" style={{ width: 40, textAlign: "right", fontSize: 10, color: "var(--muted)" }}>{pct}%</span></div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// --- Fire Evidence · fusion & validation -------------------------------------------------------

const SIGNALS: Array<[string, number]> = [
  ["VIIRS detections · 6 passes", 12], ["MODIS detections · 3 passes", 4], ["Sensor confidence", 3], ["FRP & brightness temperature", 4], ["Repeat detections · 3 days", 6], ["Sensor agreement · 5 of 5", 3],
  ["Regional satellite · Himawari-9", 9], ["Sentinel-2 smoke plume", 4], ["Local news · NLP: forest fire", 8], ["Geographic match · 3.2 km", 3], ["Temporal match · +4 h 20 min", 2], ["Government report · none yet", 0],
  ["Observation sufficiency · 3 cloudy passes", -3], ["Source reliability adjustment", -2],
];
const LADDER = ["Strong multi-source fire evidence", "Externally corroborated fire event", "Highly likely fire", "Possible fire · needs more evidence", "Likely non-fire thermal source", "No external corroboration yet", "Insufficient evidence"];

export function EvidenceFusion() {
  const x = lin(0, 100, 276, 640);
  const rowH = 35;
  let running = 35;
  const tone = (i: number, v: number) => (v < 0 ? C.red : i < 6 ? C.obs : C.ext);
  return (
    <div className="fs-page">
      <PageHead
        eyebrow="04 · Fire Evidence · fusion & validation"
        title="All evidence, weighed together"
        sub="Each signal moves the evidence score up or down according to its strength and reliability. The result is explained, never just a label."
        right={<><Chip>15 signals</Chip><Chip>reliability-weighted</Chip></>}
      />
      <div className="grid fill" style={{ gridTemplateColumns: "1.45fr 0.85fr 1fr" }}>
        <Card title="How the evidence score was built" meta="starting point → contribution of each signal">
          <Chart w={680} h={620}>
            {[0, 20, 40, 60, 80, 100].map((v) => <g key={v}><line x1={x(v)} x2={x(v)} y1={8} y2={584} stroke="#162238" /><text x={x(v)} y={604} textAnchor="middle" className="ax">{v}</text></g>)}
            <text x={266} y={28} textAnchor="end" className="an" style={{ fill: "#fff", fontWeight: 700 }}>Starting point (place & season prior)</text>
            <rect x={x(0)} y={12} width={x(35) - x(0)} height={24} fill="#5b6f8f" rx={2} /><text x={x(35) + 6} y={28} className="ax">35</text>
            {SIGNALS.map(([label, v], i) => {
              const from = running;
              running += v;
              const [a, b] = [Math.min(from, running), Math.max(from, running)];
              const yy = 12 + (i + 1) * rowH;
              return (
                <g key={label}>
                  <text x={266} y={yy + 16} textAnchor="end" className="an" style={{ fill: "var(--muted)" }}>{label}</text>
                  <rect x={x(a)} y={yy} width={Math.max(2, x(b) - x(a))} height={24} fill={tone(i, v)} rx={2} opacity={v === 0 ? 0.5 : 1} />
                  <text x={x(b) + 6} y={yy + 16} className="ax">{v > 0 ? `+${v}` : v === 0 ? "±0" : v}</text>
                </g>
              );
            })}
            <text x={266} y={12 + 15 * rowH + 16} textAnchor="end" className="an" style={{ fill: "#fff", fontWeight: 700 }}>System evidence score</text>
            <rect x={x(0)} y={12 + 15 * rowH} width={x(88) - x(0)} height={24} fill={C.inf} rx={2} /><text x={x(88) + 6} y={12 + 15 * rowH + 16} className="ax" style={{ fill: "var(--inf)" }}>88</text>
          </Chart>
        </Card>
        <Card title="Validation status">
          <div className="col" style={{ gap: 7 }}>
            {LADDER.map((l, i) => (
              <div key={l} className="inner row" style={{ justifyContent: "space-between", ...(i === 1 ? { borderColor: C.ext, background: "rgba(62,207,142,0.1)", fontWeight: 700 } : { color: "var(--muted)" }) }}>
                {l}<span className="mono" style={{ fontSize: 8.5, color: "var(--dim)" }}>{i === 0 ? "needs official report" : i === 1 ? "current" : ""}</span>
              </div>
            ))}
          </div>
          <p className="fine">“Confirmed fire” is used only with authoritative or ground-based confirmation.</p>
        </Card>
        <div className="col">
          <Card accent={C.inf} title="System evidence score">
            <div className="row" style={{ gap: 16 }}>
              <svg viewBox="0 0 100 100" style={{ width: 92, height: 92, flex: "none" }}>
                <circle cx={50} cy={50} r={42} fill="none" stroke="#1a2740" strokeWidth={8} />
                <circle cx={50} cy={50} r={42} fill="none" stroke={C.inf} strokeWidth={8} strokeLinecap="round" strokeDasharray={`${0.88 * 263.9} 263.9`} transform="rotate(-90 50 50)" />
                <text x={50} y={54} textAnchor="middle" style={{ fontSize: 26, fontWeight: 700, fill: "#fff", fontFamily: "var(--head)" }}>88</text><text x={50} y={68} textAnchor="middle" className="ax">/ 100</text>
              </svg>
              <div><p style={{ fontSize: 12 }}>How strongly the available evidence supports <b>“this is a real forest fire”</b>.</p><p className="fine" style={{ marginTop: 6 }}>A system evidence score, not an 88% probability of fire. Calibration needs a labelled set of past fires.</p></div>
            </div>
          </Card>
          <Card title="Why · in plain language" className="grow">
            <p style={{ fontSize: 12.5, lineHeight: 1.65 }}>
              <b>VIIRS</b> detected a high-confidence daytime thermal anomaly, seen again on 9 passes over 3 days by <b>all five sensors</b>. <b>Himawari-9</b> recorded a thermal anomaly at the same place, starting 21 minutes earlier, and <b>Sentinel-2</b> shows a smoke plume.{" "}
              <b>Two local news reports</b> describe a forest fire 3–4 km away, the first published 4 h 20 min after detection. <b>No official confirmation</b> is available yet, and three passes were partly cloudy.
            </p>
            <p className="card-h">What would change this</p>
            <p className="note"><b style={{ color: C.ext }}>▲</b>&nbsp; A forest department report → <b style={{ color: "var(--text)" }}>Strong multi-source fire evidence</b></p>
            <p className="note"><b style={{ color: C.red }}>▼</b>&nbsp; Two clear passes with no heat and no new reports → <b style={{ color: "var(--text)" }}>Highly likely fire, decaying</b></p>
            <Link to="/fire-evidence/case" className="btn" style={{ marginTop: "auto" }}>Open the full fire case →</Link>
          </Card>
        </div>
      </div>
    </div>
  );
}

// --- Fire Evidence · full fire case panel ------------------------------------------------------

export function FireCase() {
  const [tab, setTab] = useState("Overview");
  const dots = useMemo(() => {
    const r = rng(15);
    return Array.from({ length: 46 }, () => [EVT[0] - 14 + (r() - 0.5) * 62, EVT[1] + 6 + (r() - 0.5) * 50, r()] as [number, number, number]);
  }, []);
  const ext: Array<[string, string, string]> = [["Himawari-9 thermal anomaly", "✓", C.ext], ["Sentinel-2 smoke plume", "✓", C.ext], ["Local news · 2 articles", "✓ 3–4 km", C.ext], ["Video post · resident", "✓ ≈ 5 km", C.ext], ["Government report", "none yet", C.yellow]];
  return (
    <div className="fs-page">
      <div className="fs-head" style={{ alignItems: "center" }}>
        <p className="eyebrow" style={{ margin: 0, color: "var(--muted)" }}>Fire case</p>
        <span className="mono" style={{ fontSize: 19, fontWeight: 700 }}>{EVENT.id}</span>
        <span style={{ color: "var(--soft)" }}>East Sundarbans · Sharankhola Range, Bagerhat, Bangladesh</span>
        <div className="fs-head-right"><Chip tone={C.ext}>Externally corroborated fire event</Chip><Chip tone={C.inf}>Expanding</Chip><Chip tone={C.ext}>Evidence 88 / 100</Chip><Chip tone={C.red}>Highly unusual</Chip><button type="button" className="btn inline" onClick={() => window.print()}>Download evidence report</button></div>
      </div>
      <div className="grid fill" style={{ gridTemplateColumns: "1.05fr 2.8fr" }}>
        <Card style={{ padding: 0, overflow: "hidden", minHeight: 420 }}>
          <LocalMap viewBox="180 40 500 640" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
            <Corridor scale={0.72} />
            {dots.map(([x, y, v], i) => <circle key={i} cx={x} cy={y} r={3} fill={v > 0.7 ? "#f2c94c" : v > 0.3 ? "#f28b3c" : "#ef5350"} />)}
          </LocalMap>
          <div className="float row wrap" style={{ left: 12, bottom: 12, right: 12, gap: 4 }}>
            {["Overview", "Satellite", "Evidence", "History", "Forecast", "Exposure"].map((t) => <button key={t} type="button" className="chip sm" style={t === tab ? { borderColor: "var(--line2)", background: "#1a2a45", color: "#fff" } : { background: "rgba(10,16,28,0.8)" }} onClick={() => setTab(t)}>{t}</button>)}
          </div>
        </Card>
        <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gridTemplateRows: "minmax(0, 1fr) minmax(0, 1fr)" }}>
          <Card accent={C.obs} n="1" title="Satellite information">
            <div><KV k="Sensor" v="VIIRS · NOAA-20" /><KV k="Detection time" v="22 Mar · 07:52 UTC" /><KV k="Coordinates" v="22.127 N, 89.818 E" /><KV k="FRP" v="96.4 MW" /><KV k="Brightness temp." v="367.2 K" /><KV k="Confidence" v="high" /><KV k="Day / night" v="day" /></div>
            <p className="note" style={{ fontSize: 10.5 }}>Pixel 375 m · fire somewhere inside the pixel, not the whole pixel burning.</p>
          </Card>
          <Card accent={C.inf} n="2" title="Event information">
            <div><KV k="Event ID" v={EVENT.id} /><KV k="Start" v="20 Mar · 07:41 UTC" /><KV k="Duration" v="2 d 0 h · active" /><KV k="Behaviour state" v="Expanding" color={C.inf} /><KV k="Observations" v="63 · 9 passes" /><KV k="Sensors" v="5 of 5" /><KV k="Spread" v="12.6 km²" /></div>
          </Card>
          <Card accent={C.obs} n="3" title="Observation quality">
            <div><KV k="Sensor agreement" v="5 of 5 sensors" /><KV k="Observation sufficiency" v="0.78" /><KV k="Cloudy passes" v="3 of 12" /><KV k="Uncertainty" v="± 18% activity" /><KV k="Provenance" v="FIRMS NRT · v1.3" /></div>
            <div className="row" style={{ marginTop: 4 }}><Bar value={0.78} color={C.ext} /></div>
          </Card>
          <Card accent={C.ext} n="4" title="External evidence">
            <div>{ext.map(([k, v, tone]) => <div key={k} className="kv" style={{ alignItems: "center" }}><span style={{ color: "var(--soft)" }}>{k}</span><Chip sm tone={tone}>{v}</Chip></div>)}</div>
          </Card>
          <Card accent={C.ext} n="5" title="Validation">
            <b style={{ fontSize: 13 }}>Externally corroborated fire event</b>
            <p className="big" style={{ fontSize: 30 }}>88<small className="mono">/ 100</small></p>
            <p className="note" style={{ fontSize: 11 }}>Five sensors, Himawari-9, Sentinel-2 and three local reports agree on a forest fire at this place and time. No official confirmation yet.</p>
            <Link to="/fire-evidence/fusion" className="chip sm" style={{ alignSelf: "flex-start", marginTop: "auto" }}>How the score was built →</Link>
          </Card>
          <Card accent={C.inf} n="6" title="Historical comparison">
            <div><KV k="Similar past events" v="5 · k-NN" /><KV k="Closest" v="FS-BD-2021-0388" /><KV k="Typical duration" v="3 – 7 d (median 4.5)" /><KV k="Expanded after day 2" v="4 of 5" /><KV k="Decay began" v="day 3 – 4" /></div>
            <p className="note" style={{ fontSize: 11 }}>Context from history, not a prediction.</p>
            <Link to="/fire-past" className="chip sm" style={{ alignSelf: "flex-start", marginTop: "auto" }}>Open Fire Past →</Link>
          </Card>
          <Card accent={C.fc} n="7" title="Forecast">
            <div><KV k="6 h corridor" v="3.1 km²" /><KV k="12 h corridor" v="12.4 km²" /><KV k="24 h corridor" v="41 km²" /><KV k="Direction" v="north-east" /><KV k="Next observation" v="NOAA-21 · 19:41 UTC" /></div>
            <p className="note" style={{ fontSize: 11 }}>Where new satellite detections may appear, not physical spread.</p>
            <Link to="/fire-future" className="chip sm" style={{ alignSelf: "flex-start", marginTop: "auto" }}>Open Fire Future →</Link>
          </Card>
          <Card accent={C.fc} n="8" title="Exposure · 24 h">
            <div><KV k="Population (≤ 3 km)" v="≈ 3,400" /><KV k="Roads" v="6 km local road" /><KV k="Agriculture" v="4.2 km²" /><KV k="Protected areas" v="1 · wildlife sanctuary" /><KV k="Infrastructure" v="11 kV line · 2 forest camps" /></div>
            <p className="note" style={{ fontSize: 11 }}>Inside or near the corridor, not necessarily affected.</p>
            <Link to="/exposure" className="chip sm" style={{ alignSelf: "flex-start", marginTop: "auto" }}>Open Exposure →</Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
