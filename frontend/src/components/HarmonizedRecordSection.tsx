import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, Layers, Map as MapIcon, Users } from "lucide-react";
import { computed, HeadlineData, useSiteData, useSnapshotMeta } from "../api/harmonized";
import { useLanguage } from "../context/LanguageContext";
import HarmonizedProvenance, { StatusPill } from "./HarmonizedProvenance";
import "../harmonized.css";

/** Lightweight hook for scroll-triggered directional reveal with replay on scroll down */
function useScrollReveal<T extends HTMLElement = HTMLDivElement>(
  threshold = 0.08,
  rootMargin = "0px 0px -20px 0px"
) {
  const ref = useRef<T | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (typeof IntersectionObserver === "undefined") {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        } else {
          // If the element has moved below the viewport (scrolled back up), reset so scrolling down replays animation
          const rect = entry.boundingClientRect;
          if (rect.top > (window.innerHeight || document.documentElement.clientHeight)) {
            setIsVisible(false);
          }
        }
      },
      { threshold, rootMargin }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, rootMargin]);

  return [ref, isVisible] as const;
}

/** Home-page section: harmonized record headline, raw → events, links to the record pages. */
export default function HarmonizedRecordSection() {
  const { t, fmt } = useLanguage();
  const { data } = useSiteData();
  const { meta } = useSnapshotMeta();
  const h = data ? computed<HeadlineData>(data.headline) : null;

  const [headerRef, isHeaderVisible] = useScrollReveal<HTMLDivElement>(0.08, "0px 0px -20px 0px");
  const [gridRef, isGridVisible] = useScrollReveal<HTMLDivElement>(0.08, "0px 0px -30px 0px");
  const [cardsRef, isCardsVisible] = useScrollReveal<HTMLDivElement>(0.08, "0px 0px -30px 0px");
  const [provenanceRef, isProvenanceVisible] = useScrollReveal<HTMLDivElement>(0.08, "0px 0px -20px 0px");

  return (
    <section className="oc-section hz-section-animated" id="harmonized-record" aria-labelledby="record-heading">
      <div
        ref={headerRef}
        className={`oc-section-header hz-anim-header ${isHeaderVisible ? "hz-anim-in" : ""}`}
      >
        <span className="oc-section-tag">{t("record_tag")}</span>
        <h2 id="record-heading" className="oc-section-title">{t("record_title")}</h2>
        <p className="oc-section-desc">{t("record_desc")}</p>
      </div>

      <div
        ref={gridRef}
        className={`oc-dashboard-grid hz-anim-grid ${isGridVisible ? "hz-anim-in" : ""}`}
      >
        <div className={`oc-dashboard-panel hz-anim-panel-left ${isGridVisible ? "hz-anim-in" : ""}`}>
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

        <div className={`oc-dashboard-panel hz-anim-panel-right ${isGridVisible ? "hz-anim-in" : ""}`}>
          <div className="oc-panel-header">
            <span className="oc-panel-title"><ArrowRight size={16} />{t("raw_to_events")}</span>
          </div>
          {h ? (
            <div className="hz-flow">
              {[h.raw_detections, h.clean_detections, h.events].map((v, i) => (
                <div
                  className={`hz-flow-step hz-anim-step ${isGridVisible ? "hz-anim-in" : ""}`}
                  style={{ "--step-idx": i } as React.CSSProperties}
                  key={v.label}
                >
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

      <div
        ref={cardsRef}
        className={`hz-card-row ${isCardsVisible ? "hz-anim-in" : ""}`}
      >
        {[
          { to: "/fire-map", icon: <MapIcon size={18} />, title: "FireNow", text: t("card_map"), dirClass: "from-left" },
          { to: "/methodology", icon: <BookOpen size={18} />, title: t("nav_method"), text: t("card_method"), dirClass: "from-center" },
          { to: "/about", icon: <Users size={18} />, title: t("nav_about"), text: t("card_about"), dirClass: "from-right" },
        ].map((c, i) => (
          <Link
            key={c.to}
            to={c.to}
            className={`oc-dashboard-panel hz-link-card hz-anim-card-item ${c.dirClass} ${isCardsVisible ? "hz-anim-in" : ""}`}
            style={{ "--card-idx": i } as React.CSSProperties}
          >
            <span className="oc-panel-title">{c.icon}{c.title}</span>
            <p>{c.text}</p>
            <span className="hz-open">{t("open")} →</span>
          </Link>
        ))}
      </div>

      <div ref={provenanceRef} className={`hz-anim-provenance-wrap ${isProvenanceVisible ? "hz-anim-in" : ""}`}>
        <HarmonizedProvenance noticeClassName="hz-anim-notice" />
      </div>
    </section>
  );
}
