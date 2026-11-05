import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, Layers, Map as MapIcon, Users } from "lucide-react";
import { computed, HeadlineData, useSiteData, useSnapshotMeta } from "../api/harmonized";
import { useLanguage } from "../context/LanguageContext";
import HarmonizedProvenance, { StatusPill } from "./HarmonizedProvenance";
import "../harmonized.css";

/** Home-page section: harmonized record headline, raw → events, links to the record pages. */
export default function HarmonizedRecordSection() {
  const { t, fmt } = useLanguage();
  const { data } = useSiteData();
  const { meta } = useSnapshotMeta();
  const h = data ? computed<HeadlineData>(data.headline) : null;

  return (
    <section className="oc-section" id="harmonized-record" aria-labelledby="record-heading">
      <div className="oc-section-header">
        <span className="oc-section-tag">{t("record_tag")}</span>
        <h2 id="record-heading" className="oc-section-title">{t("record_title")}</h2>
        <p className="oc-section-desc">{t("record_desc")}</p>
      </div>

      <div className="oc-dashboard-grid">
        <div className="oc-dashboard-panel">
          <div className="oc-panel-header">
            <span className="oc-panel-title"><Layers size={16} />{t("record_tag")}</span>
            <span className="oc-hud-tag">{meta?.window ?? "…"}</span>
          </div>
          <div className="hz-hero-number">{meta?.n_events != null ? fmt(meta.n_events) : t("awaiting")}</div>
          <div className="hz-hero-label">{t("events_in_window")}</div>
          <div className="oc-hud-body" style={{ marginTop: 14 }}>
            <div className="oc-hud-row"><span>{t("window_utc")}</span><strong>{meta?.start ?? "…"} → {meta?.end ?? "…"}</strong></div>
            <div className="oc-hud-row"><span>{t("updated")}</span><strong className="accent">{meta?.last_observation_time ?? t("awaiting")}</strong></div>
          </div>
          <p className="hz-src">Source: /meta · {meta?.now_basis ?? ""}</p>
        </div>

        <div className="oc-dashboard-panel">
          <div className="oc-panel-header">
            <span className="oc-panel-title"><ArrowRight size={16} />{t("raw_to_events")}</span>
          </div>
          {h ? (
            <div className="hz-flow">
              {[h.raw_detections, h.clean_detections, h.events].map((v) => (
                <div className="hz-flow-step" key={v.label}>
                  <div className="hz-flow-value">{v.value != null ? fmt(v.value) : t("awaiting")}</div>
                  <div className="hz-flow-label">{v.label}</div>
                  <StatusPill status={v.status} />
                </div>
              ))}
              <p className="hz-src">
                {h.low_confidence.label}: {h.low_confidence.value != null ? fmt(h.low_confidence.value) : t("awaiting")} · Source: {h.events.source}
              </p>
            </div>
          ) : (
            <StatusPill status="awaiting data" />
          )}
        </div>
      </div>

      <div className="hz-card-row">
        {[
          { to: "/fire-map", icon: <MapIcon size={18} />, title: "FireNow", text: t("card_map") },
          { to: "/methodology", icon: <BookOpen size={18} />, title: t("nav_method"), text: t("card_method") },
          { to: "/about", icon: <Users size={18} />, title: t("nav_about"), text: t("card_about") },
        ].map((c) => (
          <Link key={c.to} to={c.to} className="oc-dashboard-panel hz-link-card">
            <span className="oc-panel-title">{c.icon}{c.title}</span>
            <p>{c.text}</p>
            <span className="hz-open">{t("open")} →</span>
          </Link>
        ))}
      </div>
      <HarmonizedProvenance />
    </section>
  );
}
