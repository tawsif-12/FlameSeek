import React, { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import "./pipeline-carousel.css";
import {
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  ExternalLink,
  Clock,
  Globe2,
  Crosshair,
  ShieldAlert,
  Layers,
  Compass,
  AlertTriangle,
  Activity,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

export interface PipelineStage {
  id: string;
  n: string;
  title: string;
  badge: string;
  q: string;
  how: string;
  route: string;
  method: string;
  cycle: string;
  standard: string;
  accentColor: string;
  glowColor: string;
}

export const PIPELINE_STAGES_DATA: PipelineStage[] = [
  {
    id: "memory",
    n: "01",
    title: "Burning Calendar",
    badge: "Fire history",
    q: "When does this place usually have fire activity?",
    how: "Browse past detections and compare seasons where enough data is available. Missing dates stay unknown.",
    route: "/fire-calendar",
    method: "Compare past observations",
    cycle: "Available historical dates",
    standard: "Depends on data coverage",
    accentColor: "#38bdf8",
    glowColor: "rgba(56, 189, 248, 0.55)",
  },
  {
    id: "now",
    n: "02",
    title: "Fire Now",
    badge: "Recent detections",
    q: "Where have satellites detected heat recently?",
    how: "Explore NASA fire detections on a 3D map. Select a point to see when it was observed and which satellite recorded it.",
    route: "/fire-map",
    method: "NASA MODIS and VIIRS",
    cycle: "Recent satellite passes",
    standard: "Heat does not confirm wildfire",
    accentColor: "#00f2fe",
    glowColor: "rgba(0, 242, 254, 0.55)",
  },
  {
    id: "identity",
    n: "03",
    title: "Fire Identity",
    badge: "Related detections",
    q: "Which detections may belong to the same fire?",
    how: "Group nearby observations using their locations, times and satellite pixel sizes. A group is an estimate, not a confirmed fire boundary.",
    route: "/fire-map",
    method: "Match by place and time",
    cycle: "Across nearby observations",
    standard: "Estimated fire groups",
    accentColor: "#a855f7",
    glowColor: "rgba(168, 85, 247, 0.55)",
  },
  {
    id: "evidence",
    n: "04",
    title: "Fire Evidence",
    badge: "Supporting reports",
    q: "What other evidence is available?",
    how: "Check other satellite passes, official reports and news where available. Read the original sources to understand what supports a result.",
    route: "/fire-map",
    method: "Compare independent sources",
    cycle: "As reports become available",
    standard: "Sources linked when available",
    accentColor: "#22c55e",
    glowColor: "rgba(34, 197, 94, 0.55)",
  },
  {
    id: "past",
    n: "05",
    title: "Fire Past",
    badge: "Similar past events",
    q: "What happened in similar past fires?",
    how: "Look for past events with similar conditions. These comparisons provide context, but do not tell us exactly what will happen next.",
    route: "/fire-map",
    method: "Find similar past events",
    cycle: "Available historical records",
    standard: "A comparison, not a prediction",
    accentColor: "#f59e0b",
    glowColor: "rgba(245, 158, 11, 0.55)",
  },
  {
    id: "future",
    n: "06",
    title: "Fire Future",
    badge: "Possible future activity",
    q: "Where might fire activity appear next?",
    how: "Estimate possible activity over the next 6 to 24 hours when enough data and validation are available. Unsupported forecasts are withheld.",
    route: "/fire-map",
    method: "Check data and model results",
    cycle: "6, 12 and 24 hours ahead",
    standard: "Shown only when supported",
    accentColor: "#ff7a45",
    glowColor: "rgba(255, 122, 69, 0.55)",
  },
  {
    id: "exposure",
    n: "07",
    title: "Exposure",
    badge: "Nearby people and places",
    q: "Who and what could be nearby?",
    how: "Use population and map data to identify nearby communities, roads and facilities. Results depend on the available fire area or forecast.",
    route: "/fire-map",
    method: "Population and map data",
    cycle: "For the selected analysis",
    standard: "Possible exposure, not damage",
    accentColor: "#ef4444",
    glowColor: "rgba(239, 68, 68, 0.55)",
  },
];

/* Custom Animated SVG Telemetry Visuals for Each Stage */
function StageHudGraphic({ stageId, color }: { stageId: string; color: string }) {
  switch (stageId) {
    case "memory":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          <defs>
            <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.35" />
              <stop offset="100%" stopColor={color} stopOpacity="0.0" />
            </linearGradient>
          </defs>
          {/* Grid lines */}
          <line x1="20" y1="20" x2="300" y2="20" stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />
          <line x1="20" y1="60" x2="300" y2="60" stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />
          <line x1="20" y1="100" x2="300" y2="100" stroke="rgba(255,255,255,0.12)" />
          {/* Confidence Band (MAD) */}
          <path
            d="M 20 75 Q 60 55 100 68 T 180 50 T 250 40 T 300 48 L 300 85 Q 250 78 180 82 T 100 88 T 20 90 Z"
            fill="url(#memGrad)"
          />
          {/* Baseline Median */}
          <path
            d="M 20 80 Q 60 62 100 75 T 180 62 T 250 55 T 300 64"
            fill="none"
            stroke="rgba(255,255,255,0.4)"
            strokeWidth="1.5"
            strokeDasharray="3 3"
          />
          {/* Dynamic Anomaly Fire Wave */}
          <path
            d="M 20 85 Q 60 80 90 70 T 140 30 T 200 45 T 260 22 T 300 35"
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          {/* PELT Change point markers */}
          <circle cx="140" cy="30" r="4" fill="#ffffff" stroke={color} strokeWidth="2" />
          <circle cx="260" cy="22" r="5" fill="#ff4d26" stroke="#ffffff" strokeWidth="1.5" />
          <text x="148" y="26" fill={color} fontSize="9" fontFamily="monospace">CHANGE</text>
          <text x="268" y="18" fill="#ff4d26" fontSize="9" fontFamily="monospace">UNUSUAL</text>
        </svg>
      );

    case "now":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* 3D Globe Radar Grids */}
          <circle cx="160" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.08)" />
          <circle cx="160" cy="60" r="35" fill="none" stroke="rgba(255,255,255,0.12)" strokeDasharray="3 3" />
          <ellipse cx="160" cy="60" rx="50" ry="20" fill="none" stroke="rgba(255,255,255,0.15)" />
          <line x1="160" y1="5" x2="160" y2="115" stroke="rgba(255,255,255,0.1)" strokeDasharray="2 2" />
          {/* Orbital Track line */}
          <path d="M 60 100 Q 140 40 260 20" fill="none" stroke={color} strokeWidth="2" />
          {/* Sensor Scan Footprint Trapezoid */}
          <polygon
            points="145,52 175,52 195,82 125,82"
            fill="rgba(0, 242, 254, 0.15)"
            stroke={color}
            strokeWidth="1.5"
            strokeDasharray="4 2"
          />
          {/* Active Hotspot Pulses */}
          <circle cx="155" cy="68" r="4" fill="#ff4d26" />
          <circle cx="155" cy="68" r="9" fill="none" stroke="#ff4d26" strokeWidth="1" opacity="0.6" />
          <circle cx="170" cy="72" r="3" fill="#ffaa00" />
          <text x="70" y="32" fill={color} fontSize="9" fontFamily="monospace">SATELLITE HEAT DETECTIONS</text>
          <text x="210" y="98" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace">AREA OBSERVED</text>
        </svg>
      );

    case "identity":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* FIRE GROUP Cluster Polygon (Convex Hull) */}
          <polygon
            points="70,40 130,25 210,35 240,75 190,100 100,90"
            fill="rgba(168, 85, 247, 0.12)"
            stroke={color}
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />
          {/* Cluster connection network */}
          <line x1="100" y1="50" x2="140" y2="40" stroke="rgba(168,85,247,0.3)" />
          <line x1="140" y1="40" x2="180" y2="60" stroke="rgba(168,85,247,0.3)" />
          <line x1="180" y1="60" x2="160" y2="85" stroke="rgba(168,85,247,0.3)" />
          <line x1="100" y1="50" x2="120" y2="78" stroke="rgba(168,85,247,0.3)" />
          {/* Nodes */}
          <circle cx="100" cy="50" r="3" fill="#ffffff" />
          <circle cx="140" cy="40" r="4" fill={color} />
          <circle cx="180" cy="60" r="3" fill="#ffffff" />
          <circle cx="160" cy="85" r="4" fill={color} />
          <circle cx="120" cy="78" r="3" fill="#ffffff" />
          {/* Centroid Reticle */}
          <circle cx="150" cy="62" r="8" fill="none" stroke="#ff4d26" strokeWidth="1.5" />
          <line x1="140" y1="62" x2="160" y2="62" stroke="#ff4d26" strokeWidth="1.5" />
          <line x1="150" y1="52" x2="150" y2="72" stroke="#ff4d26" strokeWidth="1.5" />
          <text x="165" y="60" fill="#ffffff" fontSize="9" fontFamily="monospace">CENTRE</text>
          <text x="35" y="25" fill={color} fontSize="9" fontFamily="monospace">RELATED DETECTIONS</text>
        </svg>
      );

    case "evidence":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* Center Target & Satellite Multi-Orbit Ring */}
          <circle cx="160" cy="60" r="45" fill="rgba(34, 197, 94, 0.06)" stroke="rgba(34, 197, 94, 0.2)" />
          <circle cx="160" cy="60" r="28" fill="none" stroke={color} strokeDasharray="3 3" />
          {/* Satellite Nodes on Circle */}
          <circle cx="160" cy="15" r="5" fill="#38bdf8" />
          <circle cx="205" cy="60" r="5" fill="#00f2fe" />
          <circle cx="160" cy="105" r="5" fill="#22c55e" />
          <circle cx="115" cy="60" r="5" fill="#f59e0b" />
          {/* Verification Cross Beams */}
          <line x1="160" y1="15" x2="160" y2="105" stroke="rgba(34,197,94,0.3)" strokeDasharray="2 2" />
          <line x1="115" y1="60" x2="205" y2="60" stroke="rgba(34,197,94,0.3)" strokeDasharray="2 2" />
          {/* Central Verified Shield */}
          <circle cx="160" cy="60" r="10" fill={color} />
          <path d="M 156 60 L 159 63 L 165 57" fill="none" stroke="#000000" strokeWidth="2" strokeLinecap="round" />
          <text x="180" y="22" fill="#38bdf8" fontSize="8" fontFamily="monospace">TERRA</text>
          <text x="215" y="64" fill="#00f2fe" fontSize="8" fontFamily="monospace">AQUA</text>
          <text x="175" y="108" fill="#22c55e" fontSize="8" fontFamily="monospace">S-NPP</text>
          <text x="65" y="64" fill="#f59e0b" fontSize="8" fontFamily="monospace">NOAA-20</text>
        </svg>
      );

    case "past":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* Coordinate axes */}
          <line x1="40" y1="15" x2="40" y2="105" stroke="rgba(255,255,255,0.2)" />
          <line x1="40" y1="105" x2="300" y2="105" stroke="rgba(255,255,255,0.2)" />
          {/* Mahalanobis Distance Ellipsoids */}
          <ellipse cx="170" cy="55" rx="90" ry="35" fill="none" stroke="rgba(245, 158, 11, 0.15)" transform="rotate(-15 170 55)" />
          <ellipse cx="170" cy="55" rx="55" ry="22" fill="none" stroke="rgba(245, 158, 11, 0.35)" transform="rotate(-15 170 55)" />
          <ellipse cx="170" cy="55" rx="25" ry="10" fill="none" stroke={color} strokeWidth="1.5" transform="rotate(-15 170 55)" />
          {/* Historic Analogues Data points */}
          <circle cx="130" cy="68" r="3" fill="rgba(255,255,255,0.4)" />
          <circle cx="195" cy="42" r="3" fill="rgba(255,255,255,0.4)" />
          <circle cx="215" cy="50" r="3" fill="rgba(255,255,255,0.4)" />
          <circle cx="150" cy="48" r="3" fill="rgba(255,255,255,0.4)" />
          {/* Current Query Point */}
          <circle cx="170" cy="55" r="5" fill="#ff4d26" stroke="#ffffff" strokeWidth="1.5" />
          <text x="50" y="30" fill={color} fontSize="9" fontFamily="monospace">SIMILAR PAST EVENTS</text>
          <text x="185" y="60" fill="#ffffff" fontSize="9" fontFamily="monospace">CURRENT EVENT</text>
        </svg>
      );

    case "future":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* Wind Vector Vector Arrow */}
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />
            </marker>
          </defs>
          <line x1="40" y1="30" x2="90" y2="30" stroke="#38bdf8" strokeWidth="2" markerEnd="url(#arrow)" />
          <text x="100" y="34" fill="#38bdf8" fontSize="9" fontFamily="monospace">WIND DIRECTION</text>
          {/* Active Ignition Origin */}
          <circle cx="60" cy="80" r="5" fill="#ff4d26" />
          {/* Downwind Projection Cones (6h, 12h, 24h) */}
          <path d="M 60 80 L 140 45 L 140 105 Z" fill="rgba(255, 122, 69, 0.15)" stroke={color} strokeDasharray="3 3" />
          <path d="M 140 45 L 220 30 L 220 115 L 140 105 Z" fill="rgba(255, 122, 69, 0.08)" stroke={color} strokeDasharray="4 2" />
          <path d="M 220 30 L 290 20 L 290 120 L 220 115 Z" fill="rgba(255, 122, 69, 0.04)" stroke={color} strokeDasharray="5 3" />
          <text x="110" y="78" fill="#ffffff" fontSize="9" fontFamily="monospace">+6h</text>
          <text x="175" y="78" fill="#ffffff" fontSize="9" fontFamily="monospace">+12h</text>
          <text x="245" y="78" fill="#ffffff" fontSize="9" fontFamily="monospace">+24h OUTLOOK</text>
        </svg>
      );

    case "exposure":
      return (
        <svg viewBox="0 0 320 120" className="pipeline-hud-svg" aria-hidden="true">
          {/* Vulnerability Grid Heatmap */}
          <rect x="30" y="20" width="260" height="80" rx="6" fill="rgba(239, 68, 68, 0.05)" stroke="rgba(239, 68, 68, 0.2)" />
          {/* Road infrastructure lines */}
          <path d="M 30 75 Q 120 70 180 50 T 290 40" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="2" />
          <path d="M 120 20 L 120 100" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" strokeDasharray="4 4" />
          {/* Critical Facilities (Hospitals, Schools) */}
          <rect x="150" y="35" width="12" height="12" rx="2" fill="#ef4444" />
          <text x="153" y="44" fill="#ffffff" fontSize="9" fontWeight="bold">+</text>
          {/* Settlement / Population Clusters */}
          <circle cx="80" cy="50" r="14" fill="rgba(239, 68, 68, 0.25)" />
          <circle cx="80" cy="50" r="6" fill="#ef4444" />
          <circle cx="230" cy="65" r="18" fill="rgba(239, 68, 68, 0.2)" />
          <circle cx="230" cy="65" r="8" fill="#ef4444" />
          <text x="40" y="32" fill={color} fontSize="9" fontFamily="monospace">POPULATION DATA</text>
          <text x="170" y="44" fill="#ffffff" fontSize="9" fontFamily="monospace">HOSPITAL</text>
        </svg>
      );

    default:
      return null;
  }
}

export default function Pipeline3DTransition() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [hasFocus, setHasFocus] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    wrapperRef.current?.querySelectorAll("svg").forEach((svg) => {
      if (reducedMotion) svg.pauseAnimations?.();
      else svg.unpauseAnimations?.();
    });
  }, [reducedMotion]);
  const [touchStartX, setTouchStartX] = useState<number | null>(null);

  const total = PIPELINE_STAGES_DATA.length;

  const goToNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % total);
  }, [total]);

  const goToPrev = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + total) % total);
  }, [total]);

  const selectIndex = (idx: number) => {
    setCurrentIndex(idx);
  };

  // Autoplay rotation every 5 seconds, paused when user hovers
  useEffect(() => {
    if (isPaused || hasFocus || reducedMotion) return;
    const timer = setInterval(() => {
      goToPrev();
    }, 5000);
    return () => clearInterval(timer);
  }, [isPaused, hasFocus, reducedMotion, goToPrev]);

  // Touch and swipe handling
  const handleTouchStart = (e: React.TouchEvent) => {
    setTouchStartX(e.touches[0].clientX);
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX === null) return;
    const diff = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(diff) > 40) {
      if (diff > 0) goToPrev();
      else goToNext();
    }
    setTouchStartX(null);
  };

  // Shortest circular offset calculation
  const getOffset = (idx: number): number => {
    let diff = idx - currentIndex;
    if (diff > total / 2) diff -= total;
    if (diff < -total / 2) diff += total;
    return diff;
  };

  const activeStage = PIPELINE_STAGES_DATA[currentIndex];

  return (
    <div
      className="pipe-transition-wrapper"
      ref={wrapperRef}
      onFocusCapture={() => setHasFocus(true)}
      onBlurCapture={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHasFocus(false); }}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      role="region"
      aria-label="7-Stage Pipeline Card Transition System"
    >
      {/* ====================================================================
          TOP INTERACTIVE PIPELINE SEQUENCER TRACK
          ==================================================================== */}
      <div className="pipe-sequencer-bar" aria-label="Pipeline sequence stages">
        {PIPELINE_STAGES_DATA.map((stage, idx) => {
          const isActive = currentIndex === idx;
          return (
            <button
              key={stage.id}
              type="button"
              className={`pipe-seq-step ${isActive ? "active" : ""}`}
              onClick={() => selectIndex(idx)}
              aria-pressed={isActive}
              style={{
                "--step-accent": stage.accentColor,
                "--step-glow": stage.glowColor,
              } as React.CSSProperties}
            >
              <div className="pipe-seq-dot">
                <span className="pipe-seq-num">{stage.n}</span>
              </div>
              <span className="pipe-seq-label">{stage.title}</span>
              {idx < total - 1 && <span className="pipe-seq-arrow">→</span>}
            </button>
          );
        })}
      </div>

      {/* ====================================================================
          3D PERSPECTIVE CAROUSEL STAGE
          ==================================================================== */}
      <div className="pipe-stage-container">
        {PIPELINE_STAGES_DATA.map((stage, idx) => {
          const offset = getOffset(idx);
          const isCenter = offset === 0;

          const level = Math.abs(offset);

          return (
            <div
              key={stage.id}
              className={`pipe-3d-card ${isCenter ? "active-center" : "flanking-card"}`}
              style={{
                "--card-direction": Math.sign(offset),
                zIndex: 10 - level,
                "--card-accent": stage.accentColor,
                "--card-glow": stage.glowColor,
              } as React.CSSProperties}
              data-level={level}
              aria-current={isCenter ? "true" : undefined}
              onClick={() => selectIndex(idx)}
              role="group"
              tabIndex={level <= 1 ? 0 : -1}
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectIndex(idx); }
                if (e.key === "ArrowLeft") { e.preventDefault(); goToPrev(); }
                if (e.key === "ArrowRight") { e.preventDefault(); goToNext(); }
              }}
              aria-label={`Select stage ${stage.n}: ${stage.title}`}
            >
              {/* Card Top Header */}
              <div className="pipe-card-top">
                <div className="pipe-card-num-badge">
                  <span className="pipe-pill-pulse" />
                  <span>STEP {stage.n}</span>
                </div>
                <span className="pipe-card-category-badge">{stage.badge}</span>
              </div>

              {/* Graphic Telemetry HUD Window */}
              <div className="pipe-card-hud-viewport">
                <StageHudGraphic stageId={stage.id} color={stage.accentColor} />
                <div className="pipe-hud-scanline" /><span style={{ position: "absolute", bottom: 4, right: 8, fontSize: 10, color: "var(--oc-text-muted)" }}>Example illustration</span>
              </div>

              {/* Card Body & Technical Metadata */}
              <div className="pipe-card-content">
                <h3 className="pipe-card-title">{stage.title}</h3>
                <div className="pipe-card-question">{stage.q}</div>

                <div className="pipe-specs-grid">
                  <div className="pipe-spec-box">
                    <span className="pipe-spec-label">HOW IT WORKS</span>
                    <strong className="pipe-spec-val">{stage.method}</strong>
                  </div>
                  <div className="pipe-spec-box">
                    <span className="pipe-spec-label">TIME PERIOD</span>
                    <strong className="pipe-spec-val">{stage.cycle}</strong>
                  </div>
                  <div className="pipe-spec-box">
                    <span className="pipe-spec-label">KEEP IN MIND</span>
                    <strong className="pipe-spec-val">{stage.standard}</strong>
                  </div>
                </div>

                <p className="pipe-card-narrative">{stage.how}</p>

                {isCenter && (
                  <div className="pipe-card-action-bar">
                    <Link
                      to={stage.route}
                      className="pipe-card-cta"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <span>Open tool</span>
                      <ArrowRight size={14} />
                    </Link>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Navigation Arrows */}
      <button
        type="button"
        className="pipe-nav-arrow pipe-arrow-prev"
        onClick={goToPrev}
        aria-label="Previous pipeline stage"
      >
        <ChevronLeft size={24} />
      </button>

      <button
        type="button"
        className="pipe-nav-arrow pipe-arrow-next"
        onClick={goToNext}
        aria-label="Next pipeline stage"
      >
        <ChevronRight size={24} />
      </button>

      {/* Bottom Counter Bar */}
      <div className="pipe-bottom-summary">
        <span className="pipe-summary-counter">
          <strong>{activeStage.n}</strong> / {String(total).padStart(2, "0")}
        </span>
        <span className="pipe-summary-text">
          Active Evidence Filter: <span style={{ color: activeStage.accentColor }}>{activeStage.title}</span> — {activeStage.badge}
        </span>
      </div>
    </div>
  );
}

