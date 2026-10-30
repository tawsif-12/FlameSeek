import { useEffect, useState } from "react";
import Plot from "react-plotly.js";
import { normalizeApiError, runJob, startEvidence, startOutlook } from "../api/client";
import type { CaseKind, CaseMarker, EvidenceCheck, EvidenceResult, FireCase, FireEvent, ForecastHorizon, HotspotRecord, Job, ModelMetrics, OutlookResult } from "../types/api";

type Tab = "Case" | "Satellite" | "Event" | "Quality" | "Evidence" | "Past" | "Future" | "Exposure";
const TABS: Tab[] = ["Case", "Satellite", "Event", "Quality", "Evidence", "Past", "Future", "Exposure"];
const TAB_LABEL: Record<Tab, string> = { Case: "Summary", Satellite: "Sighting", Event: "Fire story", Quality: "Reliability", Evidence: "Sources", Past: "Past fires", Future: "Forecast", Exposure: "Nearby" };
export const BEHAVIOUR_PLAIN: Record<string, string> = {
  Onset: "Just started",
  Intensifying: "Getting stronger",
  Expanding: "Spreading",
  Persistent: "Burning for days",
  Stable: "Steady",
  Decaying: "Dying down",
  Uncertain: "Too early to tell",
};
const CHECK_PLAIN: Record<string, string> = {
  corroborating: "confirms the fire",
  no_match: "nothing found",
  not_applicable: "already included",
  review_available: "picture available",
  review_link: "look yourself",
  cloudy_only: "too cloudy",
  no_scene: "no picture",
  unavailable: "unavailable now",
  not_covered: "not covered",
};
const CASE_REFRESH_MS = 10 * 60 * 1000;
export const KIND_COLORS: Record<CaseKind, string> = {
  agricultural_burn: "#eab308",
  wildfire: "#ef4444",
  controlled_burn: "#a855f7",
  industrial_source: "#22d3ee",
  building_fire: "#f97316",
  volcanic: "#be123c",
  not_a_fire: "#94a3b8",
  unknown: "#e2e8f0",
};
export const KIND_LABELS: Record<CaseKind, string> = {
  agricultural_burn: "Agricultural burn",
  wildfire: "Forest or wildfire",
  controlled_burn: "Controlled burn",
  industrial_source: "Industrial heat / gas flare",
  building_fire: "Building or industrial fire",
  volcanic: "Volcanic activity",
  not_a_fire: "Not a fire",
  unknown: "Type not yet known",
};
export const REALITY_WEIGHT: Record<string, number> = {
  "Confirmed fire": 5,
  "Highly likely fire": 4,
  "Possible fire (needs verification)": 2,
  "No external confirmation yet": 2,
  "Likely non-fire thermal anomaly": 1,
};
const OUTCOME_TONE: Record<string, string> = {
  first_detection: "seen",
  seen: "seen",
  seen_stronger: "seen",
  seen_weaker: "seen",
  spread: "seen",
  clear_no_fire: "clear",
  cloud_or_smoke: "cloud",
  not_covered: "none",
  expected: "expected",
};
export const BEHAVIOUR_COLORS: Record<string, string> = {
  Onset: "#38bdf8",
  Intensifying: "#f43f5e",
  Expanding: "#f97316",
  Persistent: "#eab308",
  Stable: "#a3e635",
  Decaying: "#94a3b8",
  Uncertain: "#c4b5fd",
};
const STATUS_TONE: Record<string, string> = {
  "Confirmed Fire": "tone-strong",
  "Strong Multi-Source Fire Evidence": "tone-strong",
  "Externally Corroborated Fire Event": "tone-strong",
  "Highly Likely Fire": "tone-likely",
  "Possible Fire / Needs More Evidence": "tone-possible",
  "No External Corroboration Yet": "tone-possible",
  "Likely Non-Fire Thermal Source": "tone-nonfire",
  "Insufficient Evidence": "tone-unknown",
};
const AXIS = { gridcolor: "rgba(148,197,255,0.14)", zerolinecolor: "rgba(148,197,255,0.3)", linecolor: "rgba(148,197,255,0.3)" };
const darkPlot = { autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: "#cbd5e1", size: 10 }, margin: { l: 38, r: 34, t: 6, b: 28 }, xaxis: AXIS, yaxis: AXIS };

function fmtTime(value: string | null | undefined) {
  if (!value) return "–";
  const d = new Date(value);
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <tr><th>{k}</th><td>{v ?? "–"}</td></tr>;
}

interface Props {
  event: FireEvent;
  detection: HotspotRecord | null;
  onClose: () => void;
  onForecast: (horizon: ForecastHorizon | null, cellSize: number) => void;
  onExposure: (items: Array<{ lat: number; lon: number; name: string; category: string }>) => void;
  onCaseUpdate: (eventId: string, marker: CaseMarker) => void;
}

export default function EventPanel({ event, detection, onClose, onForecast, onExposure, onCaseUpdate }: Props) {
  const [tab, setTab] = useState<Tab>("Case");
  const [evidence, setEvidence] = useState<EvidenceResult | null>(null);
  const [evidenceJob, setEvidenceJob] = useState<Job<EvidenceResult> | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [partialCase, setPartialCase] = useState<FireCase | null>(null);
  const [outlook, setOutlook] = useState<OutlookResult | null>(null);
  const [outlookJob, setOutlookJob] = useState<Job<OutlookResult> | null>(null);
  const [outlookError, setOutlookError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState("24");

  async function loadEvidence(refresh: boolean, signal?: { cancelled: boolean }) {
    setEvidenceError(null);
    try {
      const onProgress = (job: Job<EvidenceResult>) => {
        setEvidenceJob(job);
        // Each finished evidence stream re-answers the case: show it and update the map marker right away.
        const partial = job.partial?.fire_case;
        if (partial && !signal?.cancelled) {
          setPartialCase(partial);
          onCaseUpdate(event.event_id, { ...partial.marker, evidence_checked: true, updated_at: job.partial?.updated_at });
        }
      };
      const result = await runJob(startEvidence(event.event_id, refresh), onProgress, signal);
      if (!signal?.cancelled) {
        setEvidence(result);
        setPartialCase(null);
        onCaseUpdate(event.event_id, { ...result.fire_case.marker, evidence_checked: true, updated_at: result.generated_at });
      }
    } catch (err) {
      if (!signal?.cancelled) setEvidenceError(normalizeApiError(err));
    } finally {
      if (!signal?.cancelled) setEvidenceJob(null);
    }
  }

  async function loadOutlook() {
    setOutlookError(null);
    try {
      const result = await runJob(startOutlook(event.event_id), setOutlookJob);
      setOutlook(result);
      const exposureItems = Object.entries(result.exposure.assets ?? {}).flatMap(([category, block]) =>
        block.items.filter((i) => typeof i.lat === "number").map((i) => ({ lat: i.lat as number, lon: i.lon as number, name: String(i.name), category })),
      );
      onExposure(exposureItems);
    } catch (err) {
      setOutlookError(normalizeApiError(err));
    } finally {
      setOutlookJob(null);
    }
  }

  useEffect(() => {
    const signal = { cancelled: false };
    setEvidence(null);
    setPartialCase(null);
    setOutlook(null);
    onForecast(null, 0);
    onExposure([]);
    void loadEvidence(false, signal);
    return () => {
      signal.cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event.event_id]);

  // An open case is provisional: re-gather evidence periodically so the answer and map marker follow new passes.
  const caseOpen = evidence?.fire_case.status === "open";
  useEffect(() => {
    if (!caseOpen) return;
    const signal = { cancelled: false };
    const timer = window.setInterval(() => void loadEvidence(true, signal), CASE_REFRESH_MS);
    return () => {
      signal.cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseOpen, event.event_id]);

  useEffect(() => {
    if (!outlook) return;
    const h = outlook.forecast.horizons[horizon];
    onForecast(h && h.status === "ISSUED" ? h : null, outlook.forecast.cell_size_deg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outlook, horizon]);

  const status = evidence?.inference.final_status;
  const fireCase = partialCase ?? evidence?.fire_case;
  const det = detection ?? event.detections[event.detections.length - 1];

  return (
    <aside className="event-panel" aria-label="Fire event details">
      <header className="event-panel-head">
        <div>
          <p className="eyebrow">Fire seen by satellites</p>
          {event.detections.find((d) => d.place_hint)?.place_hint && <p className="event-place">{event.detections.find((d) => d.place_hint)?.place_hint}</p>}
          <h3>
            <span className="state-dot" style={{ background: BEHAVIOUR_COLORS[event.behaviour.state] }} />
            {BEHAVIOUR_PLAIN[event.behaviour.state] ?? event.behaviour.state} · seen {event.observation_count} time{event.observation_count > 1 ? "s" : ""}
          </h3>
          {fireCase ? (
            <p className="case-chip">
              <span style={{ background: KIND_COLORS[fireCase.answer.kind.category] }} />
              {fireCase.answer.is_real.label} · {fireCase.answer.kind.decided ? fireCase.answer.kind.label : "type uncertain"} · {fireCase.answer.now.label}
              {fireCase.provisional && <em>may still change</em>}
            </p>
          ) : (
            <p className="validation-chip">{evidenceJob ? "Checking if this is a real fire…" : "Not checked yet"}</p>
          )}
          {status && <p className={`validation-chip ${STATUS_TONE[status] ?? ""}`}>Evidence strength {evidence?.inference.system_evidence_score} out of 100</p>}
        </div>
        <button type="button" aria-label="Close event details" onClick={onClose}>X</button>
      </header>
      <nav className="event-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} type="button" onClick={() => setTab(t)}>{TAB_LABEL[t]}</button>
        ))}
      </nav>
      <div className="event-panel-body">
        {tab === "Case" && <CaseTab fireCase={fireCase ?? null} updating={Boolean(partialCase)} job={evidenceJob} error={evidenceError} onRefresh={() => loadEvidence(true)} />}
        {tab === "Satellite" && <SatelliteTab det={det} event={event} />}
        {tab === "Event" && <EventTab event={event} />}
        {tab === "Quality" && <QualityTab event={event} evidence={evidence} />}
        {tab === "Evidence" && <EvidenceTab evidence={evidence} job={evidenceJob} error={evidenceError} onRefresh={() => loadEvidence(true)} />}
        {(tab === "Past" || tab === "Future" || tab === "Exposure") && !outlook && (
          <OutlookLauncher job={outlookJob} error={outlookError} onRun={loadOutlook} />
        )}
        {tab === "Past" && outlook && <PastTab outlook={outlook} />}
        {tab === "Future" && outlook && <FutureTab outlook={outlook} horizon={horizon} setHorizon={setHorizon} />}
        {tab === "Exposure" && outlook && <ExposureTab outlook={outlook} />}
      </div>
      <footer className="layer-legend-note">
        Coloured edges: <span className="obs">blue</span> what satellites saw · <span className="inf">orange</span> what we conclude · <span className="ext">green</span> what others report · <span className="fc">purple</span> what may happen next
      </footer>
    </aside>
  );
}

// --- Plain-language helpers -------------------------------------------------------------------

const KIND_PLAIN: Record<CaseKind, string> = {
  agricultural_burn: "farm burn (crop or straw burning)",
  wildfire: "forest or wild fire",
  controlled_burn: "planned, controlled burn",
  industrial_source: "hot industrial site or gas flare, not a fire",
  building_fire: "building or factory fire",
  volcanic: "volcanic activity",
  not_a_fire: "false alarm",
  unknown: "fire of an unknown type",
};
const NOW_PLAIN: Record<string, string> = {
  Active: "It is still burning.",
  Growing: "It is still burning and getting bigger.",
  Weakening: "It is getting weaker.",
  Ended: "It appears to have stopped.",
};
const STREAM_LABEL: Record<string, string> = { trigger: "First alert", background: "Background", A: "Satellite", B: "Weather satellite", C: "Report" };
const VIEW_PLAIN: Record<string, string> = { "near nadir": "directly overhead", "mid swath": "off to one side", "swath edge": "at the edge of its view" };
const SATELLITE_NAMES: Record<string, string> = { modis: "MODIS", viirs_snpp: "Suomi NPP", viirs_noaa20: "NOAA-20", viirs_noaa21: "NOAA-21" };

function plain(text: string) {
  return text
    .replace(/near nadir/g, "directly overhead")
    .replace(/mid swath/g, "off to one side")
    .replace(/swath edge/g, "at the edge of its view")
    .replace(/\bFRP\b/g, "fire power")
    .replace(/^Expanding:/, "Spreading:")
    .replace(/^Intensifying:/, "Getting stronger:")
    .replace(/Detection extent/g, "The burning area")
    .replace(/km2/g, "km²")
    .replace(/overpass window/g, "satellite pass")
    .replace("(strong match)", "(matches well)")
    .replace("(possible match)", "(may match)");
}

function fmtWhen(value: string | null | undefined) {
  if (!value) return "–";
  return new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function hoursText(h: number) {
  if (h < 1) return `${Math.round(h * 60)} minutes`;
  if (h < 48) return `${Math.round(h)} hours`;
  return `${(h / 24).toFixed(1)} days`;
}

function compass(deg: number) {
  return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][Math.round(deg / 45) % 8];
}

function satelliteName(det: { sensor: string; satellite?: string | null }) {
  if (det.sensor === "modis") return det.satellite ? `${det.satellite} (MODIS camera)` : "Terra/Aqua (MODIS camera)";
  return `${SATELLITE_NAMES[det.sensor] ?? det.sensor} (VIIRS camera)`;
}

function Tech({ title = "Technical details", children }: { title?: string; children: React.ReactNode }) {
  return (
    <details className="tech">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}

function caseHeadline(c: FireCase) {
  const kind = KIND_PLAIN[c.answer.kind.category];
  const real = c.answer.is_real.label;
  let first: string;
  if (real === "Confirmed fire") first = c.answer.kind.decided ? `This is a confirmed ${kind}.` : "This is a confirmed fire. We cannot yet tell what kind.";
  else if (real === "Highly likely fire") first = c.answer.kind.decided ? `This is very likely a real ${kind}.` : "This is very likely a real fire. We cannot yet tell what kind.";
  else if (real === "Likely non-fire thermal anomaly") first = c.answer.kind.decided ? `This is probably a ${kind}.` : "This is probably not a fire. It looks more like a hot industrial site or a false alarm.";
  else if (real === "No external confirmation yet") first = "Satellites saw strong heat here, but no other source has confirmed a fire yet.";
  else first = "This might be a fire, but there is not enough evidence to be sure.";
  return `${first} ${NOW_PLAIN[c.answer.now.label] ?? ""}`;
}

const STREAM_STATE: Record<string, string> = { pending: "checking…", done: "done", seen: "saw the fire", not_seen: "saw no heat", manual_review: "no automatic data here", unavailable: "unavailable right now", no_coverage: "does not cover this place" };

function StreamStrip({ fireCase }: { fireCase: FireCase }) {
  const st = fireCase.streams;
  const items = [
    { key: "A", title: "Later satellite passes", state: st.A.status, detail: `${st.A.passes_observed} checks so far · ${st.A.passes_expected} more expected` },
    { key: "B", title: "All-day weather satellite", state: st.B.status, detail: STREAM_STATE[st.B.status] ?? st.B.status },
    { key: "C", title: "News and officials", state: st.C.status, detail: st.C.status === "pending" ? "searching…" : st.C.reports ? `${st.C.reports} matching report${st.C.reports > 1 ? "s" : ""}` : "no report found" },
  ];
  const opened = new Date(fireCase.opened_at).getTime();
  const closes = new Date(fireCase.closes_at).getTime();
  const elapsed = Math.min(1, Math.max(0, (Date.now() - opened) / (closes - opened)));
  return (
    <div className="stream-strip">
      <div className="case-clock" title="We keep checking until every satellite has passed, or for 24 hours">
        <span>First seen {fmtWhen(fireCase.opened_at)}</span>
        <div><i style={{ width: `${(fireCase.status === "closed" ? 1 : elapsed) * 100}%` }} /></div>
        <span>{fireCase.status === "closed" ? "Checking finished" : `Final answer by ${fmtWhen(fireCase.closes_at)}`}</span>
      </div>
      <ul>
        {items.map((i, n) => (
          <li key={i.key} className={i.state === "pending" ? "pending" : "done"}>
            <b className={`stream stream-${i.key}`}>Check {n + 1}</b>
            <strong>{i.title}</strong>
            <small>{i.detail}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CaseTab({ fireCase, updating, job, error, onRefresh }: { fireCase: FireCase | null; updating: boolean; job: Job<EvidenceResult> | null; error: string | null; onRefresh: () => void }) {
  if (!fireCase) {
    return (
      <section>
        <h4>Checking this fire…</h4>
        <p className="plain-lead">A satellite spotted heat here. We are now checking three things: whether other satellites saw it too, what the all-day weather satellite shows, and whether news or officials have reported it.</p>
        {job && <JobProgress job={job} />}
        {error && <p className="evidence-error">{error}</p>}
      </section>
    );
  }
  const a = fireCase.answer;
  const rules = fireCase.decision_rules;
  const looked = fireCase.passes.filter((p) => p.outcome !== "expected" && p.outcome !== "not_covered");
  const tooFar = fireCase.passes.filter((p) => p.outcome === "not_covered").length;
  const reasons = fireCase.evidence_block
    .map((i) => ({ item: i, weight: a.kind.decided ? i.votes[rules.top] ?? 0 : Math.max(0, ...Object.values(i.votes)) }))
    .filter((r) => r.weight > 0.3)
    .sort((x, y) => y.weight - x.weight)
    .slice(0, 4);
  return (
    <>
      <section className="tag-inf">
        <div className="validation-header">
          <div>
            <p className="eyebrow">In short</p>
            <h4>{fireCase.provisional ? "What we know so far" : "What we found"}</h4>
          </div>
          <button type="button" onClick={onRefresh} disabled={Boolean(job)}>{job ? "..." : "Check again"}</button>
        </div>
        <p className="plain-lead">{caseHeadline(fireCase)}</p>
        {fireCase.provisional && <p className="note">This answer may still change as more satellites fly over{fireCase.pending_witnesses.length ? ` (still waiting for ${fireCase.pending_witnesses.join(", ")})` : ""}.</p>}
        {updating && job && <p className="case-updating"><span className="pulse-dot" />Updating as new information arrives. {job.message}…</p>}
        <StreamStrip fireCase={fireCase} />
        <ol className="case-answer">
          <li><span>Is it a real fire?</span><strong>{a.is_real.label}</strong><small>{a.is_real.basis}</small></li>
          <li>
            <span>What kind of fire?</span>
            <strong><i style={{ background: KIND_COLORS[a.kind.category] }} />{a.kind.label}</strong>
            <small>{a.kind.basis}</small>
          </li>
          <li><span>What is it doing now?</span><strong>{a.now.label}</strong><small>{a.now.basis}</small></li>
        </ol>
        {reasons.length > 0 && (
          <>
            <h4>Main reasons</h4>
            <ul className="reason-list">{reasons.map((r, i) => <li key={i}>{plain(r.item.summary)}</li>)}</ul>
          </>
        )}
        <h4>How the evidence splits between possible explanations</h4>
        <ul className="category-bars">
          {fireCase.category_scores.map((c) => (
            <li key={c.category} className={c.category === rules.top && rules.passed ? "top" : ""}>
              <span>{c.label}</span>
              <div><i style={{ width: `${c.score}%`, background: KIND_COLORS[c.category] }} /></div>
              <b>{c.score}%</b>
            </li>
          ))}
        </ul>
        <p className="note">
          We only name a type when one explanation has more than half of the evidence and is clearly ahead of the next one. {rules.passed ? "Here it does." : "Here none does, so we say the type is uncertain."} These are evidence scores, not exact probabilities.
        </p>
      </section>
      <section className="tag-obs">
        <h4>Did other satellites see it afterwards?</h4>
        <p className="note">Five fire-watching satellites fly over a few times a day. Each time one passes, we check this exact spot.</p>
        <ul className="pass-list">
          {looked.map((p, i) => (
            <li key={`${p.witness}-${p.time}-${i}`} className={`pass ${OUTCOME_TONE[p.outcome] ?? ""}`}>
              <time>{fmtWhen(p.time)}</time>
              <strong>{p.label.replace(" MODIS", "").replace(" VIIRS", "")}</strong>
              <span>
                {p.outcome_label}
                {p.frp_mw !== undefined ? ` · fire power ${p.frp_mw} MW` : ""}
                {p.cloud_cover_pct !== undefined && p.cloud_cover_pct !== null ? ` · ${Math.round(p.cloud_cover_pct)}% cloud` : ""}
              </span>
              <small>
                {VIEW_PLAIN[p.swath_position] ? `Looking from ${VIEW_PLAIN[p.swath_position]}` : ""}
                {p.detection_chance !== undefined && p.outcome === "clear_no_fire" ? ` · it had a ${Math.round(p.detection_chance * 100)}% chance of spotting a fire like this` : ""}
              </small>
            </li>
          ))}
        </ul>
        {tooFar > 0 && <p className="note">{tooFar} other pass{tooFar > 1 ? "es" : ""} flew too far to the side to see this spot.</p>}
        {fireCase.next_passes.length > 0 && <p className="note">Next satellites due: {fireCase.next_passes.map((p) => `${p.label.replace(" MODIS", "").replace(" VIIRS", "")} around ${fmtWhen(p.time)}`).join(" · ")}</p>}
      </section>
      <section className="tag-ext">
        <h4>All-day weather satellite</h4>
        <p className="note">Weather satellites stay over one side of the Earth and take a picture every 10 minutes. They are blurrier, but they show when a fire started and how long it burned.</p>
        <p>
          {fireCase.geostationary.status === "seen"
            ? `${fireCase.geostationary.satellite} saw heat here from ${fmtWhen(fireCase.geostationary.started)} to ${fmtWhen(fireCase.geostationary.last_seen)}: about ${hoursText(fireCase.geostationary.duration_hours ?? 0)}.`
            : fireCase.geostationary.detail}
        </p>
        {fireCase.geostationary.review_links.map((l) => l.review_url && <a key={l.name} href={l.review_url} target="_blank" rel="noreferrer">{l.name}</a>)}
      </section>
      <section>
        <h4>Everything we know, in time order</h4>
        <ul className="evidence-block">
          {fireCase.evidence_block.map((item, i) => (
            <li key={i} className={`ev-${item.kind}`}>
              <div>
                <b className={`stream stream-${item.stream}`}>{STREAM_LABEL[item.stream]}</b>
                <span>{item.source}</span>
                {item.time && <time>{fmtWhen(item.time)}</time>}
              </div>
              <p>{plain(item.summary)}</p>
              {Object.keys(item.votes).length > 0 && (
                <small>Points towards: {Object.entries(item.votes).sort((x, y) => y[1] - x[1]).slice(0, 2).map(([k]) => KIND_LABELS[k as CaseKind] ?? k).join(", ")}</small>
              )}
              {item.link && <a href={item.link} target="_blank" rel="noreferrer">Original source</a>}
            </li>
          ))}
        </ul>
        <Tech>
          <p className="explanation">{fireCase.explanation}</p>
          <p className="note">
            Decision rule: the top category must score above {rules.min_top_score}% and lead the next by {rules.min_lead} points. Top is {rules.top_score}% with a {rules.lead}-point lead. {fireCase.score_note}
          </p>
          <p className="note">
            Fused satellite fire probability: {Math.round(fireCase.satellite_fire_probability.probability * 100)}% from {fireCase.satellite_fire_probability.passes_used} pass(es), prior{" "}
            {Math.round(fireCase.satellite_fire_probability.prior * 100)}%. {fireCase.satellite_fire_probability.method}
          </p>
          <p className="note">Overpasses: {fireCase.overpass_method}. {fireCase.overpass_errors.join(" ")}</p>
          {fireCase.burning_season.status === "ok" && <p className="note">Burning calendar: {fireCase.burning_season.window}. {fireCase.burning_season.note}</p>}
          <ul className="note-list">{Object.values(fireCase.situations).map((t) => <li key={t}>{t}</li>)}</ul>
        </Tech>
      </section>
    </>
  );
}

function SatelliteTab({ det, event }: { det: HotspotRecord; event: FireEvent }) {
  return (
    <section className="tag-obs">
      <h4>What one satellite saw</h4>
      <p className="plain-lead">
        The {satelliteName(det)} satellite saw heat here on {fmtWhen(det.acq_datetime)}, during the {det.daynight === "N" ? "night" : "day"}.
      </p>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Satellite" v={satelliteName(det)} />
          <Row k="When" v={`${fmtWhen(det.acq_datetime)} (your local time)`} />
          <Row k="Where" v={`${det.lat.toFixed(4)}, ${det.lon.toFixed(4)}`} />
          <Row k="How exact is the location" v={det.location_uncertainty_km ? `within about ${det.location_uncertainty_km} km` : "–"} />
          <Row k="Fire power (heat given off)" v={det.frp !== null ? `${det.frp} MW` : "not provided"} />
          <Row k="Satellite's own confidence" v={`${det.confidence_pct.toFixed(0)}%`} />
        </tbody>
      </table>
      <p className="note">A satellite sees the ground as small squares. It tells us there is fire somewhere in the square, not that the whole square is burning.</p>
      <p className="note">In total, satellites saw this fire {event.detections.length} time{event.detections.length > 1 ? "s" : ""}. The strongest reading was {event.max_frp ?? "–"} MW.</p>
      <Tech>
        <table className="cesium-info-table">
          <tbody>
            <Row k="Sensor" v={`${det.sensor.toUpperCase()} (${det.satellite || "–"})`} />
            <Row k="Detection time" v={fmtTime(det.acq_datetime)} />
            <Row k="Pixel footprint" v={det.scan_km && det.track_km && det.scan_km <= 6 ? `${det.scan_km.toFixed(2)} × ${det.track_km.toFixed(2)} km` : "nominal"} />
            <Row k="Brightness temperature" v={det.brightness_k ? `${det.brightness_k} K${det.brightness_2_k ? ` / ${det.brightness_2_k} K` : ""}` : "–"} />
            <Row k="Source" v={det.source || "FIRMS"} />
            <Row k="Sensors in this event" v={event.sensors.join(", ")} />
          </tbody>
        </table>
      </Tech>
    </section>
  );
}

function EventTab({ event }: { event: FireEvent }) {
  const t = event.timeline;
  return (
    <section className="tag-inf">
      <h4>The story of this fire</h4>
      <p className="plain-lead">
        Satellites first saw this fire on {fmtWhen(event.first_detection)} and last saw it on {fmtWhen(event.latest_detection)}
        {event.duration_hours >= 1 ? `, about ${hoursText(event.duration_hours)} apart` : ""}. It has been seen {event.observation_count} time{event.observation_count > 1 ? "s" : ""} and covers about {event.extent_km2} km².
      </p>
      <h4>Right now: <span style={{ color: BEHAVIOUR_COLORS[event.behaviour.state] }}>{BEHAVIOUR_PLAIN[event.behaviour.state] ?? event.behaviour.state}</span></h4>
      <ul>{event.behaviour.reasons?.map((r) => <li key={r}>{plain(r)}</li>)}</ul>
      {t.length > 1 && (
        <>
          <Plot
            data={[
              { type: "bar", x: t.map((b) => b.window_start), y: t.map((b) => b.total_frp), name: "fire power (MW)", marker: { color: "#f97316" } },
              { type: "scatter", mode: "lines+markers", x: t.map((b) => b.window_start), y: t.map((b) => b.cumulative_extent_km2), name: "area km²", yaxis: "y2", line: { color: "#38bdf8" } },
            ]}
            layout={{ ...darkPlot, height: 170, showlegend: false, yaxis: { ...AXIS, title: { text: "fire power" } }, yaxis2: { ...AXIS, overlaying: "y", side: "right", title: { text: "km²" } } }}
            config={{ displayModeBar: false, responsive: true }}
            className="plot"
          />
          <p className="note">Orange bars: how strongly it burned in each half-day. Blue line: how much ground it has covered so far.</p>
        </>
      )}
      <p className="note">This is worked out from satellite sightings. It is not a direct measurement of the fire on the ground.</p>
      <Tech>
        <table className="cesium-info-table">
          <tbody>
            <Row k="Event ID" v={event.event_id} />
            <Row k="First / latest detection" v={`${fmtTime(event.first_detection)} / ${fmtTime(event.latest_detection)}`} />
            <Row k="Sensors" v={event.sensors.join(", ")} />
            <Row k="FRP trend" v={event.frp_trend} />
            <Row k="Extent" v={`${event.extent_km2} km² · ${event.max_span_km} km across`} />
            <Row k="Association confidence" v={event.association_confidence !== null ? `${Math.round(event.association_confidence * 100)}%` : "single detection"} />
            <Row k={event.behaviour.label_type} v={event.behaviour.state} />
          </tbody>
        </table>
        <p className="note">{event.association_note}</p>
        <p className="note">{event.behaviour.caveat}</p>
      </Tech>
    </section>
  );
}

function QualityTab({ event, evidence }: { event: FireEvent; evidence: EvidenceResult | null }) {
  const q = event.observation_quality;
  const lead =
    q.uncertainty === "low"
      ? "This sighting is reliable: several satellites saw it many times and agree with each other."
      : q.uncertainty === "moderate"
        ? "This sighting is fairly reliable, but it rests on a limited number of satellite views."
        : "Treat this sighting with care: it rests on a single satellite view.";
  return (
    <section className="tag-obs">
      <h4>How much can we trust the satellite view?</h4>
      <p className="plain-lead">{lead}</p>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Do the satellites agree?" v={q.sensor_agreement} />
          <Row k="How well could satellites see this place?" v={`${q.observation_sufficiency_score} out of 100`} />
          <Row k="Cloud cover in the last day" v={q.recent_cloud_cover_pct !== null ? `${q.recent_cloud_cover_pct}%` : "unknown"} />
          <Row k="How exact is the location" v={q.location_uncertainty_km ? `within about ${q.location_uncertainty_km} km` : "–"} />
          <Row k="If satellites see nothing next time" v={q.status_if_absent === "UNKNOWN" ? "We could not say the fire is out: clouds may be hiding it" : "It would mean the fire is no longer burning"} />
        </tbody>
      </table>
      <p className="note">Clouds and smoke block the satellites' view, so "nothing seen" only counts when the sky was clear.</p>
      <Tech>
        <p className="note">Platforms available: {q.platforms_available.join(", ")}. Overall uncertainty: {q.uncertainty}. {q.uncertainty_note}</p>
        <p className="note">Data source: {String(evidence?.observation.provenance.data_source ?? "NASA FIRMS")}</p>
        <p className="note">Processing: {String(evidence?.observation.provenance.processing ?? "Confidence filter, footprint, event linking")}</p>
        <p className="note">Sources: {(q.provenance.sources as string[] | undefined)?.join(", ")}</p>
        <p className="note">{String(q.provenance.cloud_cover_source)}</p>
      </Tech>
    </section>
  );
}

function CheckList({ checks }: { checks: EvidenceCheck[] }) {
  return (
    <ul className="check-list">
      {checks.map((c) => (
        <li key={c.name} className={`check ${c.status}`}>
          <strong>{c.name}</strong>
          <span className="check-status">{CHECK_PLAIN[c.status] ?? c.status.replace(/_/g, " ")}</span>
          {c.detail && <small>{c.detail}</small>}
          {c.scenes && c.scenes.length > 0 && (
            <small>Nearest clear picture: {fmtWhen(c.scenes[0].datetime)} · {c.scenes[0].cloud_cover_pct?.toFixed(0)}% cloud</small>
          )}
          {c.review_url && <a href={c.review_url} target="_blank" rel="noreferrer">Open to look yourself</a>}
        </li>
      ))}
    </ul>
  );
}

function EvidenceTab({ evidence, job, error, onRefresh }: { evidence: EvidenceResult | null; job: Job<EvidenceResult> | null; error: string | null; onRefresh: () => void }) {
  if (!evidence) {
    return (
      <section>
        {job && <JobProgress job={job} />}
        {error && <p className="evidence-error">{error}</p>}
        {!job && !error && <p className="note">Gathering what other sources say…</p>}
      </section>
    );
  }
  const inf = evidence.inference;
  const place = evidence.place;
  const ext = evidence.external_evidence;
  return (
    <>
      <section className="tag-inf">
        <div className="validation-header">
          <div>
            <p className="eyebrow">What other sources say</p>
            <h4 className={STATUS_TONE[inf.final_status]}>{inf.final_status}</h4>
          </div>
          <button type="button" onClick={onRefresh} disabled={Boolean(job)}>{job ? "..." : "Check again"}</button>
        </div>
        <div className="evidence-score"><span>How strong is the evidence?</span><strong>{inf.system_evidence_score} out of 100</strong></div>
        <p className="explanation">{inf.explanation}</p>
        {inf.fire_type_note && <p className="note">{inf.fire_type_note}</p>}
        {inf.uncertainty.length > 0 && (
          <>
            <h4>What we are not sure about</h4>
            <ul>{inf.uncertainty.map((u) => <li key={u} className="uncertain">{u}</li>)}</ul>
          </>
        )}
        <Tech title="How the evidence score is built">
          <table className="score-table">
            <tbody>
              {inf.components.map((c) => (
                <tr key={c.signal}><th>{c.signal}</th><td><meter min={0} max={c.max} value={c.points} /> {c.points}/{c.max}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="note">{inf.score_note}</p>
          <p className="note">{inf.confirmed_label_policy}</p>
        </Tech>
      </section>
      <section>
        <h4>Where is it?</h4>
        <p>{[place.village, place.city, place.district, place.state, place.country].filter(Boolean).join(", ") || "No named place (remote area or ocean)"}</p>
        {place.nearest_settlement && <p className="note">Nearest town or village: {place.nearest_settlement.name}, {place.nearest_settlement.distance_km} km away</p>}
        {place.land_context.protected_areas.length > 0 && <p className="note">Inside a protected area: {place.land_context.protected_areas.map((p) => p.name).join(", ")}</p>}
        {place.land_context.forests.length > 0 && <p className="note">Inside a forest: {place.land_context.forests.map((p) => p.name).join(", ")}</p>}
        {place.land_context.nearby_heat_sources.length > 0 && <p className="note warn">Other hot places nearby that can fool satellites: {place.land_context.nearby_heat_sources.map((h) => `${h.name} (${h.type.replace(/_/g, " ")}, ${h.distance_km} km)`).join("; ")}</p>}
      </section>
      <section className="tag-ext">
        <h4>Other satellites and pictures</h4>
        <CheckList checks={ext.regional_satellite.checks} />
      </section>
      <section className="tag-ext">
        <h4>Government and official reports</h4>
        {ext.official.matches.length === 0 && <p className="note">No official report found for this place and time.</p>}
        {ext.official.matches.map((m, i) => (
          <article key={i} className="news-evidence-card">
            <strong>{String(m.title ?? "Official incident")}</strong>
            <span>{String(m.source ?? "Official source")} · {String(m.distance_km)} km from the fire{m.discovered ? ` · reported ${fmtWhen(String(m.discovered))}` : ""}</span>
            {m.url ? <a href={String(m.url)} target="_blank" rel="noreferrer">Original source</a> : null}
          </article>
        ))}
        <Tech title="Which official feeds were checked">
          <CheckList checks={ext.official.checks} />
          <p className="note">{ext.official.note}</p>
        </Tech>
      </section>
      <section className="tag-ext">
        <h4>Local news</h4>
        {ext.news.articles.length === 0 ? (
          <p className="note">No news report about a fire here was found. Small rural fires are often not reported, so this does not mean there is no fire.</p>
        ) : (
          ext.news.articles.slice(0, 6).map((a) => (
            <article key={a.url ?? a.headline} className="news-evidence-card">
              <div className="source-block">
                <strong>{a.headline}</strong>
                <span>{a.publication} · {a.published_at ? fmtWhen(a.published_at) : "time unknown"}</span>
                {a.url && <a href={a.url} target="_blank" rel="noreferrer">Read the original article</a>}
              </div>
              <div className="summary-block">
                <small className="label">Our automatic summary</small>
                <p>{a.system_summary}</p>
              </div>
              <dl>
                <div><dt>What it describes</dt><dd>{a.event_type.replace(/_/g, " ").toLowerCase()}</dd></div>
                <div><dt>Place it names</dt><dd>{a.location_mentioned ?? "–"}</dd></div>
                <div><dt>Distance from the fire</dt><dd>{a.distance_km !== null ? `${a.distance_km} km` : "–"}</dd></div>
                <div><dt>How well it matches</dt><dd>{a.match_label} ({a.relevance_score}/100)</dd></div>
              </dl>
              <Tech title="Matching details">
                <p className="note">Place: {a.geographic_match}. Time: {a.temporal_match}. Source: {a.source_reliability}. Cause or impact mentioned: {[...a.nlp.causes, ...a.nlp.affected_area].join(", ") || "none"}.</p>
              </Tech>
            </article>
          ))
        )}
        <Tech title="How sources are handled">
          <p className="note">{ext.news.note}</p>
          <p className="note">{place.source}</p>
          {Object.entries(evidence.source_transparency).map(([k, v]) => <p key={k} className="note"><strong>{k.replace(/_/g, " ")}:</strong> {v}</p>)}
        </Tech>
      </section>
    </>
  );
}

function JobProgress({ job }: { job: Job<unknown> }) {
  return (
    <div className="job-progress dark" role="status">
      <div><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
      <small>{job.message}</small>
    </div>
  );
}

function OutlookLauncher({ job, error, onRun }: { job: Job<OutlookResult> | null; error: string | null; onRun: () => void }) {
  return (
    <section>
      <h4>Past fires, forecast and who is nearby</h4>
      <p className="plain-lead">We can compare this fire with similar fires from earlier years, estimate where satellites may see fire next, and list the people and places close by.</p>
      <p className="note">This takes a few seconds to a few minutes the first time, then it is saved.</p>
      {job ? <JobProgress job={job} /> : <button className="primary-button" type="button" onClick={onRun}>Show me</button>}
      {error && <p className="evidence-error">{error}</p>}
    </section>
  );
}

function PastTab({ outlook }: { outlook: OutlookResult }) {
  const a = outlook.analogues;
  if (a.status !== "ok") return <section><h4>Similar fires from earlier years</h4><p className="note">{a.note}</p></section>;
  const s = a.summary ?? {};
  const range = s.typical_duration_range_hours as number[] | undefined;
  return (
    <section className="tag-inf">
      <h4>Similar fires from earlier years</h4>
      <p className="plain-lead">
        Fires like this one, in this area and season, usually lasted about {hoursText(Number(s.median_total_duration_hours))}
        {range ? ` (from ${hoursText(range[0])} to ${hoursText(range[1])})` : ""}. {String(s.expanded_after_this_age)} of them kept growing after reaching the point this fire is at now
        {s.median_peak_frp_hours_from_start !== null && s.median_peak_frp_hours_from_start !== undefined ? `, and they were usually strongest around hour ${s.median_peak_frp_hours_from_start}` : ""}.
        {Number(s.median_remaining_hours) > 0 ? ` If this fire behaves the same way, it may burn for roughly ${hoursText(Number(s.median_remaining_hours))} more.` : " Most of them were already over by this point."}
      </p>
      <p className="note warn">Past fires give context. They do not mean this fire will behave the same way.</p>
      <Plot
        data={a.analogues.map((x) => ({ type: "scatter", mode: "lines", x: x.outcome.frp_timeline.map((p) => p.hours), y: x.outcome.frp_timeline.map((p) => p.frp), name: `${x.year}` }))}
        layout={{ ...darkPlot, height: 160, showlegend: true, legend: { font: { size: 9 } }, xaxis: { ...AXIS, title: { text: "hours since the fire started" } }, yaxis: { ...AXIS, title: { text: "fire power" } } }}
        config={{ displayModeBar: false, responsive: true }}
        className="plot"
      />
      <p className="note">Each line is one past fire: how strongly it burned over time.</p>
      {a.analogues.map((x) => (
        <article key={x.event_id} className="news-evidence-card">
          <strong>A similar fire in {x.year}</strong>
          <dl>
            <div><dt>How long it lasted</dt><dd>{hoursText(x.outcome.duration_hours)}</dd></div>
            <div><dt>Kept growing after this point?</dt><dd>{x.outcome.expanded_after_matched_age ? "yes" : "no"}</dd></div>
            <div><dt>Strongest at</dt><dd>{x.outcome.peak_frp_window_hours_from_start !== null ? `hour ${x.outcome.peak_frp_window_hours_from_start}` : "–"}</dd></div>
            <div><dt>Final size</dt><dd>{x.outcome.final_extent_km2} km²</dd></div>
          </dl>
        </article>
      ))}
      <Tech>
        <p className="note">Compared at the same age ({a.matched_age_hours} h) using {a.method?.replace(/_/g, " ")} on {a.features_used?.join(", ")}. Searched {a.candidates} past events from {outlook.history.years.length} seasons.</p>
        {a.analogues.map((x) => <p key={x.event_id} className="note">{x.year} · {x.event_id}: distance {x.distance}, most similar on {x.most_similar_on.join(", ")}; decay began {x.outcome.decay_began_hours_from_start ?? "–"} h; {x.outcome.total_detections} detections.</p>)}
        <p className="note">{a.ecological_context}</p>
        <p className="note">{a.caveat}</p>
      </Tech>
    </section>
  );
}

function MetricsTable({ models, chosen }: { models: Record<string, ModelMetrics>; chosen?: string }) {
  const names = ["persistence", "seasonal", "wind_only", "lightgbm"];
  return (
    <table className="metrics-table">
      <thead><tr><th>Model</th><th>Brier</th><th>BSS</th><th>POD</th><th>FAR</th><th>CSI</th><th>ECE</th></tr></thead>
      <tbody>
        {names.filter((n) => models[n]).map((n) => (
          <tr key={n} className={n === chosen ? "chosen" : ""}>
            <td>{n.replace("_", "-")}</td>
            <td>{models[n].brier}</td>
            <td>{models[n].brier_skill_vs_climatology ?? "–"}</td>
            <td>{models[n].probability_of_detection ?? "–"}</td>
            <td>{models[n].false_alarm_ratio ?? "–"}</td>
            <td>{models[n].critical_success_index ?? "–"}</td>
            <td>{models[n].expected_calibration_error}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FutureTab({ outlook, horizon, setHorizon }: { outlook: OutlookResult; horizon: string; setHorizon: (h: string) => void }) {
  const f = outlook.forecast;
  const h = f.horizons[horizon];
  const top = h.cells.length ? Math.round(h.cells[0].p * 100) : 0;
  const metrics = h.model_used && h.validation.temporal.status === "ok" ? h.validation.temporal.models?.[h.model_used] : undefined;
  return (
    <section className="tag-fc">
      <h4>Where satellites may see fire next</h4>
      <div className="mode-toggle">
        {Object.keys(f.horizons).map((k) => (
          <button key={k} type="button" className={k === horizon ? "active" : ""} onClick={() => setHorizon(k)}>Next {k} hours</button>
        ))}
      </div>
      {h.status === "FORECAST WITHHELD" ? (
        <div className="withheld">
          <strong>No forecast given</strong>
          <p className="note">We are not confident enough to give a forecast here, so we give none instead of guessing.</p>
          <ul>{h.reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      ) : (
        <>
          <p className="plain-lead">
            {top >= 60
              ? `In the next ${horizon} hours, satellites will very likely see fire here again (up to ${top}% chance).`
              : top >= 30
                ? `In the next ${horizon} hours, there is a moderate chance (up to ${top}%) that satellites will see fire here.`
                : `In the next ${horizon} hours, new fire activity here is unlikely (at most ${top}% chance).`}{" "}
            The coloured squares on the map show the area to watch, about {h.corridor_area_km2} km².
          </p>
          <p className="legend-row"><span className="c-low" /> small chance <span className="c-mod" /> medium chance <span className="c-high" /> high chance</p>
          {h.wind && <p className="note">Wind is blowing towards the {compass(h.wind.blowing_toward_deg)} at {h.wind.mean_speed_kmh} km/h, so smoke and sparks move that way.</p>}
          {metrics && (
            <p className="note">
              How good is this forecast? Tested on past fires, it caught about {Math.round((metrics.probability_of_detection ?? 0) * 100)} out of 100 real fire areas, and about{" "}
              {Math.round((metrics.false_alarm_ratio ?? 0) * 100)} out of 100 of its warnings were false alarms.
            </p>
          )}
        </>
      )}
      <p className="note warn">This shows where satellites may detect fire, not exactly how the fire will spread. A place outside the coloured area can still burn.</p>
      <Tech title="Technical details: model and testing">
        <p className="note">{f.target}</p>
        {h.status === "ISSUED" && <p className="note">Valid {fmtTime(h.valid_from)} → {fmtTime(h.valid_to)} · model: <strong>{h.model_used?.replace("_", "-")}</strong> · corridor ≈ {h.corridor_area_km2} km² (p ≥ 0.1)</p>}
        {h.model_selection && <p className="note">{h.model_selection}</p>}
        {h.wind && <p className="note">Wind toward {h.wind.blowing_toward_deg}° at {h.wind.mean_speed_kmh} km/h · RH {h.wind.mean_rh_pct}%</p>}
        {h.validation.temporal.status === "ok" && (
          <>
            <h4>Validation: {h.validation.temporal.split}</h4>
            <MetricsTable models={h.validation.temporal.models!} chosen={h.model_used} />
          </>
        )}
        {h.validation.spatial.status === "ok" && (
          <>
            <h4>Validation: {h.validation.spatial.split}</h4>
            <MetricsTable models={h.validation.spatial.models!} chosen={h.model_used} />
          </>
        )}
        {metrics?.reliability && (
          <Plot
            data={[
              { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], line: { color: "#475569", dash: "dot" }, name: "perfect" },
              { type: "scatter", mode: "lines+markers", x: metrics.reliability.map((r) => r.mean_forecast), y: metrics.reliability.map((r) => r.observed_frequency), name: "calibration", line: { color: "#f97316" } },
            ]}
            layout={{ ...darkPlot, height: 170, showlegend: false, xaxis: { ...AXIS, title: { text: "forecast probability" }, range: [0, 1] }, yaxis: { ...AXIS, title: { text: "observed" }, range: [0, 1] } }}
            config={{ displayModeBar: false, responsive: true }}
            className="plot"
          />
        )}
        {h.training && <p className="note">Trained on {h.training.samples.toLocaleString()} cell samples ({h.training.positives} positive) from {h.training.issue_times} issue times in {h.training.years.join(", ")}.</p>}
        {h.feature_importance && Object.keys(h.feature_importance).length > 0 && (
          <p className="note">LightGBM feature importance: {Object.entries(h.feature_importance).slice(0, 5).map(([k]) => k.replace(/_/g, " ")).join(", ")}</p>
        )}
        <p className="note">Inputs: {f.inputs_used.join("; ")}. Not used: {f.inputs_not_used.join("; ")}.</p>
        <p className="note">{f.caveat}</p>
      </Tech>
    </section>
  );
}

function ExposureTab({ outlook }: { outlook: OutlookResult }) {
  const e = outlook.exposure;
  if (e.status !== "ok") return <section><h4>People and places nearby</h4><p className="note">{e.note}</p></section>;
  const people = e.population?.population;
  const count = (key: string) => e.assets?.[key]?.count ?? 0;
  return (
    <section className="tag-fc">
      <h4>People and places nearby</h4>
      <p className="plain-lead">
        {people !== null && people !== undefined ? `About ${people.toLocaleString()} people live in or near the area to watch (${e.corridor_area_km2} km²).` : `The area to watch covers about ${e.corridor_area_km2} km².`}{" "}
        It includes {count("settlements")} town{count("settlements") === 1 ? "" : "s"} or village{count("settlements") === 1 ? "" : "s"}, {count("schools")} school{count("schools") === 1 ? "" : "s"} and {count("hospitals")} hospital{count("hospitals") === 1 ? "" : "s"} or clinic{count("hospitals") === 1 ? "" : "s"}.
      </p>
      <p className="note warn">These people and places are close to where fire may be seen next. We do not claim they will be affected.</p>
      <table className="cesium-info-table">
        <tbody>
          {Object.entries(e.assets ?? {}).map(([key, block]) => (
            <Row key={key} k={block.label} v={block.status !== "ok" ? "unavailable" : key === "roads" ? `${block.length_km_inside_corridor} km of main road` : `${block.count ?? 0}`} />
          ))}
        </tbody>
      </table>
      {Object.entries(e.assets ?? {}).filter(([, b]) => b.items.length > 0).map(([key, block]) => (
        <details key={key}>
          <summary>{block.label}</summary>
          <ul>
            {block.items.slice(0, 12).map((i, idx) => (
              <li key={idx}>{String(i.name)}{i.km_inside ? ` · ${String(i.km_inside)} km inside the area` : ""}{i.population_tag ? ` · about ${Number(i.population_tag).toLocaleString()} people` : ""}</li>
            ))}
          </ul>
        </details>
      ))}
      <Tech title="Where these numbers come from">
        <p className="note">Area: {e.corridor_area_km2} km² ({e.corridor_cells} cells, any horizon, p ≥ 0.1).</p>
        <p className="note">{e.population?.dataset} {e.population?.note}</p>
        <p className="note">Sources: {e.sources?.join("; ")}</p>
        {e.errors && e.errors.length > 0 && <p className="note warn">Partially unavailable: {e.errors.join("; ")}</p>}
      </Tech>
    </section>
  );
}
