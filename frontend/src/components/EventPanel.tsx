import { useEffect, useState } from "react";
import Plot from "react-plotly.js";
import { normalizeApiError, runJob, startEvidence, startOutlook } from "../api/client";
import type { CaseKind, CaseMarker, EvidenceCheck, EvidenceResult, FireCase, FireEvent, ForecastHorizon, HotspotRecord, Job, ModelMetrics, OutlookResult } from "../types/api";

type Tab = "Case" | "Satellite" | "Event" | "Quality" | "Evidence" | "Past" | "Future" | "Exposure";
const TABS: Tab[] = ["Case", "Satellite", "Event", "Quality", "Evidence", "Past", "Future", "Exposure"];
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
const darkPlot = { autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: "#cbd5e1", size: 10 }, margin: { l: 38, r: 34, t: 6, b: 28 } };

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
  const [outlook, setOutlook] = useState<OutlookResult | null>(null);
  const [outlookJob, setOutlookJob] = useState<Job<OutlookResult> | null>(null);
  const [outlookError, setOutlookError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState("24");

  async function loadEvidence(refresh: boolean, signal?: { cancelled: boolean }) {
    setEvidenceError(null);
    try {
      const result = await runJob(startEvidence(event.event_id, refresh), setEvidenceJob, signal);
      if (!signal?.cancelled) {
        setEvidence(result);
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
  const fireCase = evidence?.fire_case;
  const det = detection ?? event.detections[event.detections.length - 1];

  return (
    <aside className="event-panel" aria-label="Fire event details">
      <header className="event-panel-head">
        <div>
          <p className="eyebrow">Fire Event · {event.event_id}</p>
          <h3>
            <span className="state-dot" style={{ background: BEHAVIOUR_COLORS[event.behaviour.state] }} />
            {event.behaviour.state} · {event.observation_count} detection{event.observation_count > 1 ? "s" : ""}
          </h3>
          {fireCase ? (
            <p className="case-chip">
              <span style={{ background: KIND_COLORS[fireCase.answer.kind.category] }} />
              {fireCase.answer.is_real.label} · {fireCase.answer.kind.decided ? fireCase.answer.kind.label : "type uncertain"} · {fireCase.answer.now.label}
              {fireCase.provisional && <em>provisional</em>}
            </p>
          ) : (
            <p className="validation-chip">{evidenceJob ? "Case open: gathering evidence..." : "Case open: evidence pending"}</p>
          )}
          {status && <p className={`validation-chip ${STATUS_TONE[status] ?? ""}`}>{status} · {evidence?.inference.system_evidence_score}/100</p>}
        </div>
        <button type="button" aria-label="Close event details" onClick={onClose}>X</button>
      </header>
      <nav className="event-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} type="button" onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <div className="event-panel-body">
        {tab === "Case" && <CaseTab fireCase={fireCase ?? null} job={evidenceJob} error={evidenceError} onRefresh={() => loadEvidence(true)} />}
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
        <span className="obs">Observation</span> what satellites recorded · <span className="inf">Inference</span> what the system concludes · <span className="ext">External</span> what independent sources report · <span className="fc">Forecast</span> what may be observed next
      </footer>
    </aside>
  );
}

function CaseTab({ fireCase, job, error, onRefresh }: { fireCase: FireCase | null; job: Job<EvidenceResult> | null; error: string | null; onRefresh: () => void }) {
  if (!fireCase) {
    return (
      <section>
        <h4>Fire Case</h4>
        <p className="note">This detection opened a case. Later satellite passes, geostationary satellites, news and official reports are being gathered into one evidence block.</p>
        {job && <JobProgress job={job} />}
        {error && <p className="evidence-error">{error}</p>}
      </section>
    );
  }
  const a = fireCase.answer;
  const rules = fireCase.decision_rules;
  const pastPasses = fireCase.passes.filter((p) => p.outcome !== "expected");
  return (
    <>
      <section className="tag-inf">
        <div className="validation-header">
          <div>
            <p className="eyebrow">Fire Case · {fireCase.status === "open" ? `open until ${fmtTime(fireCase.closes_at)}` : "closed"}</p>
            <h4>The answer {fireCase.provisional && <small>(provisional)</small>}</h4>
          </div>
          <button type="button" onClick={onRefresh} disabled={Boolean(job)}>{job ? "..." : "Recheck"}</button>
        </div>
        <ol className="case-answer">
          <li><span>Is it real?</span><strong>{a.is_real.label}</strong><small>{a.is_real.basis}</small></li>
          <li>
            <span>What kind?</span>
            <strong><i style={{ background: KIND_COLORS[a.kind.category] }} />{a.kind.label}</strong>
            <small>{a.kind.basis}</small>
          </li>
          <li><span>What is it doing now?</span><strong>{a.now.label}</strong><small>{a.now.basis}</small></li>
        </ol>
        {fireCase.pending_witnesses.length > 0 && fireCase.status === "open" && <p className="note">Still waiting for: {fireCase.pending_witnesses.join(", ")}.</p>}
        <h4>Category evidence scores</h4>
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
          Decision rules: the top category must score above {rules.min_top_score}% and lead the next by {rules.min_lead} points. The top scores {rules.top_score}% with a {rules.lead}-point lead, so{" "}
          {rules.passed ? "the type is named" : "no type is named"}. {fireCase.score_note}
        </p>
        <p className="note">
          Satellite fire probability (fused from every look within 12 h): <strong>{Math.round(fireCase.satellite_fire_probability.probability * 100)}%</strong> from{" "}
          {fireCase.satellite_fire_probability.passes_used} pass(es), prior {Math.round(fireCase.satellite_fire_probability.prior * 100)}%.
        </p>
        <h4>Plain-language explanation</h4>
        <p className="explanation">{fireCase.explanation}</p>
      </section>
      <section className="tag-obs">
        <h4>Stream A · later satellite passes</h4>
        <ul className="pass-list">
          {pastPasses.map((p, i) => (
            <li key={`${p.witness}-${p.time}-${i}`} className={`pass ${OUTCOME_TONE[p.outcome] ?? ""}`}>
              <time>{fmtTime(p.time)}</time>
              <strong>{p.label}</strong>
              <span>
                {p.outcome_label}
                {p.frp_mw !== undefined ? ` · ${p.frp_mw} MW` : ""}
                {p.cloud_cover_pct !== undefined && p.cloud_cover_pct !== null ? ` · cloud ${Math.round(p.cloud_cover_pct)}%` : ""}
              </span>
              {p.swath_position !== "unknown" && <small>{p.swath_position}</small>}
            </li>
          ))}
        </ul>
        {fireCase.next_passes.length > 0 && <p className="note">Next passes: {fireCase.next_passes.map((p) => `${p.label} ${fmtTime(p.time)}`).join(" · ")}</p>}
        <p className="note">Overpasses: {fireCase.overpass_method}. {fireCase.overpass_errors.join(" ")}</p>
      </section>
      <section className="tag-ext">
        <h4>Stream B · geostationary satellites</h4>
        <p className="note">
          {fireCase.geostationary.status === "seen"
            ? `${fireCase.geostationary.satellite} saw it from ${fmtTime(fireCase.geostationary.started)} to ${fmtTime(fireCase.geostationary.last_seen)} (${fireCase.geostationary.duration_hours} h).`
            : fireCase.geostationary.detail}
        </p>
        {fireCase.geostationary.review_links.map((l) => l.review_url && <a key={l.name} href={l.review_url} target="_blank" rel="noreferrer">{l.name}</a>)}
        <p className="note">Stream C (news and official reports) is listed in the evidence block below and in full on the Evidence tab.</p>
      </section>
      <section>
        <h4>Evidence block (time-ordered)</h4>
        <ul className="evidence-block">
          {fireCase.evidence_block.map((item, i) => (
            <li key={i} className={`ev-${item.kind}`}>
              <div>
                <b className={`stream stream-${item.stream}`}>{item.stream === "background" ? "Background" : item.stream === "trigger" ? "Trigger" : `Stream ${item.stream}`}</b>
                <span>{item.source}</span>
                {item.time && <time>{fmtTime(item.time)}</time>}
              </div>
              <p>{item.summary}</p>
              {Object.keys(item.votes).length > 0 && (
                <small>
                  Votes (reliability {item.reliability}): {Object.entries(item.votes).map(([k, v]) => `${KIND_LABELS[k as CaseKind] ?? k} +${v}`).join(", ")}
                </small>
              )}
              {item.link && <a href={item.link} target="_blank" rel="noreferrer">Original source</a>}
            </li>
          ))}
        </ul>
        {fireCase.burning_season.status === "ok" && <p className="note">Burning calendar: {fireCase.burning_season.window}. {fireCase.burning_season.note}</p>}
        <ul className="note-list">{Object.values(fireCase.situations).map((t) => <li key={t}>{t}</li>)}</ul>
      </section>
    </>
  );
}

function SatelliteTab({ det, event }: { det: HotspotRecord; event: FireEvent }) {
  return (
    <section className="tag-obs">
      <h4>Selected detection <small>(original satellite observation)</small></h4>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Sensor" v={`${det.sensor.toUpperCase()} (${det.satellite || "–"})`} />
          <Row k="Detection time" v={fmtTime(det.acq_datetime)} />
          <Row k="Coordinates" v={`${det.lat.toFixed(4)}, ${det.lon.toFixed(4)}`} />
          <Row k="Location uncertainty" v={det.location_uncertainty_km ? `± ${det.location_uncertainty_km} km (pixel footprint + geolocation)` : "–"} />
          <Row k="Pixel footprint" v={det.scan_km && det.track_km && det.scan_km <= 6 ? `${det.scan_km.toFixed(2)} × ${det.track_km.toFixed(2)} km` : "nominal"} />
          <Row k="FRP" v={det.frp !== null ? `${det.frp} MW` : "not provided"} />
          <Row k="Brightness" v={det.brightness_k ? `${det.brightness_k} K${det.brightness_2_k ? ` / ${det.brightness_2_k} K` : ""}` : "–"} />
          <Row k="Confidence" v={`${det.confidence_pct.toFixed(0)}%`} />
          <Row k="Day/Night" v={det.daynight === "N" ? "Night" : "Day"} />
          <Row k="Source" v={det.source || "FIRMS"} />
        </tbody>
      </table>
      <p className="note">A pixel with a detection is not a burned pixel; the fire may cover only a small part of the footprint.</p>
      <h4>All detections in this event</h4>
      <p className="note">{event.detections.length} detections from {event.sensors.join(", ")} · peak FRP {event.max_frp ?? "–"} MW</p>
    </section>
  );
}

function EventTab({ event }: { event: FireEvent }) {
  const t = event.timeline;
  return (
    <section className="tag-inf">
      <h4>Fire identity <small>(system reconstruction)</small></h4>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Event ID" v={event.event_id} />
          <Row k="First detection" v={fmtTime(event.first_detection)} />
          <Row k="Latest detection" v={fmtTime(event.latest_detection)} />
          <Row k="Duration" v={`${event.duration_hours} h`} />
          <Row k="Observations" v={event.observation_count} />
          <Row k="Sensors" v={event.sensors.join(", ")} />
          <Row k="FRP trend" v={event.frp_trend} />
          <Row k="Geographic spread" v={`${event.extent_km2} km² detection extent · ${event.max_span_km} km across`} />
          <Row k="Association confidence" v={event.association_confidence !== null ? `${Math.round(event.association_confidence * 100)}%` : "single detection"} />
        </tbody>
      </table>
      <p className="note">{event.association_note}</p>
      <h4>{event.behaviour.label_type}: <span style={{ color: BEHAVIOUR_COLORS[event.behaviour.state] }}>{event.behaviour.state}</span></h4>
      <ul>{event.behaviour.reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
      <p className="note">{event.behaviour.caveat}</p>
      {t.length > 1 && (
        <Plot
          data={[
            { type: "bar", x: t.map((b) => b.window_start), y: t.map((b) => b.total_frp), name: "FRP (MW)", marker: { color: "#f97316" } },
            { type: "scatter", mode: "lines+markers", x: t.map((b) => b.window_start), y: t.map((b) => b.cumulative_extent_km2), name: "extent km²", yaxis: "y2", line: { color: "#38bdf8" } },
          ]}
          layout={{ ...darkPlot, height: 170, showlegend: false, yaxis: { title: { text: "FRP" } }, yaxis2: { overlaying: "y", side: "right", title: { text: "km²" } } }}
          config={{ displayModeBar: false, responsive: true }}
          className="plot"
        />
      )}
    </section>
  );
}

function QualityTab({ event, evidence }: { event: FireEvent; evidence: EvidenceResult | null }) {
  const q = event.observation_quality;
  return (
    <section className="tag-obs">
      <h4>Observation quality and uncertainty</h4>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Sensor agreement" v={q.sensor_agreement} />
          <Row k="Observation sufficiency" v={`${q.observation_sufficiency_score}/100`} />
          <Row k="Platforms available" v={q.platforms_available.join(", ")} />
          <Row k="Recent cloud cover" v={q.recent_cloud_cover_pct !== null ? `${q.recent_cloud_cover_pct}% (24 h mean)` : "unknown"} />
          <Row k="Location uncertainty" v={q.location_uncertainty_km ? `up to ± ${q.location_uncertainty_km} km` : "–"} />
          <Row k="Overall uncertainty" v={q.uncertainty} />
          <Row k="If no detection now" v={q.status_if_absent === "UNKNOWN" ? "UNKNOWN (clouds could hide fire)" : "absence would be a valid observation"} />
        </tbody>
      </table>
      <p className="note">{q.uncertainty_note}</p>
      <h4>Provenance</h4>
      <p className="note">Data source: {String(evidence?.observation.provenance.data_source ?? "NASA FIRMS")}</p>
      <p className="note">Processing: {String(evidence?.observation.provenance.processing ?? "Confidence filter, footprint, event linking")}</p>
      <p className="note">Sources: {(q.provenance.sources as string[] | undefined)?.join(", ")}</p>
      <p className="note">{String(q.provenance.cloud_cover_source)}</p>
    </section>
  );
}

function CheckList({ checks }: { checks: EvidenceCheck[] }) {
  return (
    <ul className="check-list">
      {checks.map((c) => (
        <li key={c.name} className={`check ${c.status}`}>
          <strong>{c.name}</strong>
          <span className="check-status">{c.status.replace(/_/g, " ")}</span>
          {c.detail && <small>{c.detail}</small>}
          {c.scenes && c.scenes.length > 0 && (
            <small>Nearest clear scene: {fmtTime(c.scenes[0].datetime)} · {c.scenes[0].cloud_cover_pct?.toFixed(0)}% cloud</small>
          )}
          {c.review_url && <a href={c.review_url} target="_blank" rel="noreferrer">Open for review</a>}
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
        {!job && !error && <p className="note">Waiting for evidence...</p>}
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
            <p className="eyebrow">System interpretation</p>
            <h4 className={STATUS_TONE[inf.final_status]}>{inf.final_status}</h4>
          </div>
          <button type="button" onClick={onRefresh} disabled={Boolean(job)}>{job ? "..." : "Refresh"}</button>
        </div>
        <div className="evidence-score"><span>System Evidence Score</span><strong>{inf.system_evidence_score} / 100</strong></div>
        <p className="note">{inf.score_note}</p>
        {inf.observation_sufficiency !== null && inf.observation_sufficiency !== undefined && (
          <p className="note">Observation sufficiency at this location: {inf.observation_sufficiency}/100{inf.status_note ? ` · ${inf.status_note}` : ""}</p>
        )}
        <table className="score-table">
          <tbody>
            {inf.components.map((c) => (
              <tr key={c.signal}><th>{c.signal}</th><td><meter min={0} max={c.max} value={c.points} /> {c.points}/{c.max}</td></tr>
            ))}
          </tbody>
        </table>
        <h4>Why</h4>
        <p className="explanation">{inf.explanation}</p>
        {inf.fire_type_note && <p className="note">{inf.fire_type_note}</p>}
        {inf.uncertainty.length > 0 && <ul>{inf.uncertainty.map((u) => <li key={u} className="uncertain">{u}</li>)}</ul>}
        <p className="note">{inf.confirmed_label_policy}</p>
      </section>
      <section>
        <h4>Location (reverse geocoding)</h4>
        <p>{[place.village, place.city, place.district, place.state, place.country].filter(Boolean).join(", ") || "No named place (remote area or ocean)"}</p>
        {place.nearest_settlement && <p className="note">Nearest settlement: {place.nearest_settlement.name} ({place.nearest_settlement.type}, {place.nearest_settlement.distance_km} km)</p>}
        {place.land_context.protected_areas.length > 0 && <p className="note">Protected area: {place.land_context.protected_areas.map((p) => p.name).join(", ")}</p>}
        {place.land_context.forests.length > 0 && <p className="note">Forest: {place.land_context.forests.map((p) => p.name).join(", ")}</p>}
        {place.land_context.nearby_heat_sources.length > 0 && <p className="note warn">Nearby known heat sources: {place.land_context.nearby_heat_sources.map((h) => `${h.name} (${h.type.replace(/_/g, " ")}, ${h.distance_km} km)`).join("; ")}</p>}
        <p className="note">{place.source}</p>
      </section>
      <section className="tag-ext">
        <h4>Regional satellite verification</h4>
        <CheckList checks={ext.regional_satellite.checks} />
      </section>
      <section className="tag-ext">
        <h4>Government and official sources</h4>
        <CheckList checks={ext.official.checks} />
        {ext.official.matches.map((m, i) => (
          <article key={i} className="news-evidence-card">
            <strong>{String(m.title ?? "Official incident")}</strong>
            <span>{String(m.incident_type ?? "").replace(/_/g, " ").toLowerCase()} · {String(m.distance_km)} km away{m.discovered ? ` · discovered ${fmtTime(String(m.discovered))}` : ""}</span>
            {m.url ? <a href={String(m.url)} target="_blank" rel="noreferrer">Original source</a> : null}
          </article>
        ))}
        <p className="note">{ext.official.note}</p>
      </section>
      <section className="tag-ext">
        <h4>Local news</h4>
        {ext.news.articles.length === 0 ? (
          <p className="note">No fire-related report matched{ext.news.searched.gdelt_error ? ` (news search error: ${String(ext.news.searched.gdelt_error)})` : ""}.</p>
        ) : (
          ext.news.articles.slice(0, 6).map((a) => (
            <article key={a.url} className="news-evidence-card">
              <div className="source-block">
                <small className="label">Original source</small>
                <strong>{a.headline}</strong>
                <span>{a.publication} · {a.published_at ? fmtTime(a.published_at) : "time unknown"}</span>
                {a.url && <a href={a.url} target="_blank" rel="noreferrer">Open original article</a>}
              </div>
              <div className="summary-block">
                <small className="label">System-generated summary (rule-based NLP)</small>
                <p>{a.system_summary}</p>
              </div>
              <dl>
                <div><dt>Event type</dt><dd>{a.event_type.replace(/_/g, " ").toLowerCase()}</dd></div>
                <div><dt>Reported location</dt><dd>{a.location_mentioned ?? "–"}</dd></div>
                <div><dt>Distance</dt><dd>{a.distance_km !== null ? `${a.distance_km} km` : "–"}</dd></div>
                <div><dt>Relevance</dt><dd>{a.relevance_score}/100 · {a.match_label}</dd></div>
                <div><dt>Geographic match</dt><dd>{a.geographic_match}</dd></div>
                <div><dt>Temporal match</dt><dd>{a.temporal_match}</dd></div>
                <div><dt>Source reliability</dt><dd>{a.source_reliability}</dd></div>
                <div><dt>Cause / impact</dt><dd>{[...a.nlp.causes, ...a.nlp.affected_area].join(", ") || "–"}</dd></div>
              </dl>
            </article>
          ))
        )}
        <p className="note">{ext.news.note}</p>
      </section>
      <section>
        <h4>Source transparency</h4>
        {Object.entries(evidence.source_transparency).map(([k, v]) => <p key={k} className="note"><strong>{k.replace(/_/g, " ")}:</strong> {v}</p>)}
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
      <h4>Historical analogues, forecast and exposure</h4>
      <p className="note">
        This downloads the same season from the last 8 years around this event (about 1 to 4 minutes the first time, then cached). It reconstructs historical events, trains
        and validates the forecast models, and overlays the forecast corridor with population and infrastructure.
      </p>
      {job ? <JobProgress job={job} /> : <button className="primary-button" type="button" onClick={onRun}>Run analysis</button>}
      {error && <p className="evidence-error">{error}</p>}
    </section>
  );
}

function PastTab({ outlook }: { outlook: OutlookResult }) {
  const a = outlook.analogues;
  if (a.status !== "ok") return <section><h4>Fire Past</h4><p className="note">{a.note}</p></section>;
  return (
    <section className="tag-inf">
      <h4>Similar historical events</h4>
      <p className="note">Compared at the same age ({a.matched_age_hours} h) using {a.method?.replace(/_/g, " ")} on {a.features_used?.join(", ")}. Searched {a.candidates} past events from {outlook.history.years.length} seasons.</p>
      <table className="cesium-info-table">
        <tbody>
          {Object.entries(a.summary ?? {}).map(([k, v]) => <Row key={k} k={k.replace(/_/g, " ")} v={Array.isArray(v) ? v.join(" – ") : String(v)} />)}
        </tbody>
      </table>
      <Plot
        data={a.analogues.map((x) => ({ type: "scatter", mode: "lines", x: x.outcome.frp_timeline.map((p) => p.hours), y: x.outcome.frp_timeline.map((p) => p.frp), name: `${x.year}` }))}
        layout={{ ...darkPlot, height: 160, showlegend: true, legend: { font: { size: 9 } }, xaxis: { title: { text: "hours from first detection" } }, yaxis: { title: { text: "FRP" } } }}
        config={{ displayModeBar: false, responsive: true }}
        className="plot"
      />
      {a.analogues.map((x) => (
        <article key={x.event_id} className="news-evidence-card">
          <strong>{x.year} · {x.event_id}</strong>
          <span>similarity distance {x.distance} · most similar on {x.most_similar_on.join(", ")}</span>
          <dl>
            <div><dt>Lasted</dt><dd>{x.outcome.duration_hours} h</dd></div>
            <div><dt>Expanded after this age</dt><dd>{x.outcome.expanded_after_matched_age ? "yes" : "no"}</dd></div>
            <div><dt>FRP peak at</dt><dd>{x.outcome.peak_frp_window_hours_from_start ?? "–"} h</dd></div>
            <div><dt>Decay began</dt><dd>{x.outcome.decay_began_hours_from_start ?? "–"} h</dd></div>
            <div><dt>Final extent</dt><dd>{x.outcome.final_extent_km2} km²</dd></div>
            <div><dt>Detections</dt><dd>{x.outcome.total_detections}</dd></div>
          </dl>
        </article>
      ))}
      <p className="note">{a.ecological_context}</p>
      <p className="note warn">{a.caveat}</p>
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
  return (
    <section className="tag-fc">
      <h4>Fire Future: activity corridor</h4>
      <p className="note">{f.target}</p>
      <div className="mode-toggle">
        {Object.keys(f.horizons).map((k) => (
          <button key={k} type="button" className={k === horizon ? "active" : ""} onClick={() => setHorizon(k)}>{k} h</button>
        ))}
      </div>
      {h.status === "FORECAST WITHHELD" ? (
        <div className="withheld">
          <strong>FORECAST WITHHELD</strong>
          <ul>{h.reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      ) : (
        <>
          <p className="note">Valid {fmtTime(h.valid_from)} → {fmtTime(h.valid_to)} · model: <strong>{h.model_used?.replace("_", "-")}</strong> · corridor ≈ {h.corridor_area_km2} km² (p ≥ 0.1)</p>
          <p className="note">{h.model_selection}</p>
          {h.wind && <p className="note">Wind toward {h.wind.blowing_toward_deg}° at {h.wind.mean_speed_kmh} km/h · RH {h.wind.mean_rh_pct}%</p>}
          <p className="legend-row"><span className="c-low" /> 5–30% <span className="c-mod" /> 30–60% <span className="c-high" /> ≥ 60% chance of a detection in the cell</p>
        </>
      )}
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
      {h.validation.temporal.status === "ok" && h.model_used && h.validation.temporal.models?.[h.model_used]?.reliability && (
        <Plot
          data={[
            { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], line: { color: "#475569", dash: "dot" }, name: "perfect" },
            { type: "scatter", mode: "lines+markers", x: h.validation.temporal.models[h.model_used].reliability.map((r) => r.mean_forecast), y: h.validation.temporal.models[h.model_used].reliability.map((r) => r.observed_frequency), name: "calibration", line: { color: "#f97316" } },
          ]}
          layout={{ ...darkPlot, height: 170, showlegend: false, xaxis: { title: { text: "forecast probability" }, range: [0, 1] }, yaxis: { title: { text: "observed" }, range: [0, 1] } }}
          config={{ displayModeBar: false, responsive: true }}
          className="plot"
        />
      )}
      {h.training && <p className="note">Trained on {h.training.samples.toLocaleString()} cell samples ({h.training.positives} positive) from {h.training.issue_times} issue times in {h.training.years.join(", ")}.</p>}
      {h.feature_importance && Object.keys(h.feature_importance).length > 0 && (
        <p className="note">LightGBM feature importance: {Object.entries(h.feature_importance).slice(0, 5).map(([k]) => k.replace(/_/g, " ")).join(", ")}</p>
      )}
      <p className="note">Inputs: {f.inputs_used.join("; ")}. Not used: {f.inputs_not_used.join("; ")}.</p>
      <p className="note warn">{f.caveat}</p>
    </section>
  );
}

function ExposureTab({ outlook }: { outlook: OutlookResult }) {
  const e = outlook.exposure;
  if (e.status !== "ok") return <section><h4>Exposure</h4><p className="note">{e.note}</p></section>;
  return (
    <section className="tag-fc">
      <h4>Exposure within the possible activity corridor</h4>
      <p className="note warn">{e.wording}</p>
      <table className="cesium-info-table">
        <tbody>
          <Row k="Corridor area" v={`${e.corridor_area_km2} km² (${e.corridor_cells} cells, any horizon, p ≥ 0.1)`} />
          <Row k="Population" v={e.population?.population !== null && e.population?.population !== undefined ? `≈ ${e.population.population.toLocaleString()} people` : `unavailable (${e.population?.note ?? ""})`} />
          {Object.entries(e.assets ?? {}).map(([key, block]) => (
            <Row key={key} k={block.label} v={block.status !== "ok" ? "unavailable" : key === "roads" ? `${block.length_km_inside_corridor} km of major road` : `${block.count ?? 0}`} />
          ))}
        </tbody>
      </table>
      {Object.entries(e.assets ?? {}).filter(([, b]) => b.items.length > 0).map(([key, block]) => (
        <details key={key}>
          <summary>{block.label}</summary>
          <ul>
            {block.items.slice(0, 12).map((i, idx) => (
              <li key={idx}>{String(i.name)} {i.relation ? `· ${String(i.relation)}` : ""}{i.km_inside ? ` · ${String(i.km_inside)} km inside` : ""}{i.population_tag ? ` · pop ${String(i.population_tag)}` : ""}</li>
            ))}
          </ul>
        </details>
      ))}
      <p className="note">{e.population?.dataset} {e.population?.note}</p>
      <p className="note">Sources: {e.sources?.join("; ")}</p>
      {e.errors && e.errors.length > 0 && <p className="note warn">Partially unavailable: {e.errors.join("; ")}</p>}
    </section>
  );
}
