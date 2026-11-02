import React, { useState, useEffect, useRef } from "react";
import {
  RotateCcw,
  ShieldCheck,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  X,
  ExternalLink,
} from "lucide-react";

export interface RoadmapMilestone {
  id: string;
  num: string;
  title: string;
  question: string;
  shortDesc: string;
  fullAnswer: string;
  metric: string;
  accentColor: string;
  glowColor: string;
  // Exact 1200 x 720 canvas coordinates
  pinX: number;
  pinY: number;
  cardTopY: number;
  cardBottomY: number;
  tier: 1 | 2; // Tier 1: upper (Y: 35-175), Tier 2: lower (Y: 215-355)
}

const ROADMAP_DATA: RoadmapMilestone[] = [
  {
    id: "four-witness",
    num: "01",
    title: "Four-Witness Fleet",
    question: "Why does FlameSeek require four synchronized satellites instead of just one?",
    shortDesc: "Eliminates orbital blind spots & cloud gaps by harmonizing Terra, Aqua, Suomi NPP, and NOAA-20.",
    fullAnswer:
      "Single-sensor wildfire monitoring leaves critical blind spots: polar satellites only pass an area 1-2 times daily, cloud cover blocks observation, and burning varies drastically between morning and afternoon. By combining Terra, Aqua, Suomi NPP, and NOAA-20, FlameSeek achieves continuous day/night multi-angle coverage and eliminates orbit-drift timing artifacts.",
    metric: "4 SATELLITES • ZERO BLIND SPOTS",
    accentColor: "#38bdf8",
    glowColor: "rgba(56, 189, 248, 0.55)",
    pinX: 85,
    pinY: 510,
    cardTopY: 35,
    cardBottomY: 175,
    tier: 1,
  },
  {
    id: "obs-vs-inf",
    num: "02",
    title: "Observation vs. Inference",
    question: "What is the difference between an observation and an inference?",
    shortDesc: "Strictly separates raw thermal detections from calculated perimeters, diurnal models, and corridors.",
    fullAnswer:
      "A satellite hotspot is an observation (sensor, footprint, FRP, confidence)—not automatically a confirmed wildfire. FlameSeek categorizes inferences separately: spatio-temporal event groupings, diurnal power normalization, corroborated status, and downwind corridors. Every external report retains its original citation link.",
    metric: "RAW EVIDENCE • CITATION TRACKED",
    accentColor: "#00f2fe",
    glowColor: "rgba(0, 242, 254, 0.55)",
    pinX: 305,
    pinY: 590,
    cardTopY: 215,
    cardBottomY: 355,
    tier: 2,
  },
  {
    id: "orbit-drift",
    num: "03",
    title: "Orbit Drift Elimination",
    question: "How does the system eliminate orbit drift artifacts across 26 years?",
    shortDesc: "Normalizes 26 years of MODIS observations to Aqua 13:30 solar equivalent, maintaining climate consistency.",
    fullAnswer:
      "As Terra and Aqua aged, their orbital equator-crossing times shifted by tens of minutes, altering apparent fire counts. FlameSeek fits monthly diurnal fire power curves and projects every observation to its Aqua 13:30 solar equivalent, ensuring a scientifically consistent 2000-present climate record.",
    metric: "AQUA 13:30 EQV • 2000–PRESENT",
    accentColor: "#a855f7",
    glowColor: "rgba(168, 85, 247, 0.55)",
    pinX: 525,
    pinY: 500,
    cardTopY: 35,
    cardBottomY: 175,
    tier: 1,
  },
  {
    id: "hide-one-witness",
    num: "04",
    title: "Hide-One-Witness Test",
    question: "What is the 'Hide-One-Witness' test and how does it prevent false confidence?",
    shortDesc: "Empirically withholds NOAA-20 to test predictive precision, achieving AUC = 0.94 and verified Brier skill.",
    fullAnswer:
      "To empirically prove our fused fire probability works, FlameSeek hides NOAA-20 detections entirely from the fusion engine. The system then evaluates how accurately the remaining three satellites predict NOAA-20's actual detections, yielding an Area Under the ROC Curve (AUC) of 0.94 and verified Brier skill score.",
    metric: "AUC = 0.94 • BRIER VERIFIED",
    accentColor: "#f59e0b",
    glowColor: "rgba(245, 158, 11, 0.55)",
    pinX: 745,
    pinY: 605,
    cardTopY: 215,
    cardBottomY: 355,
    tier: 2,
  },
  {
    id: "forecast-withheld",
    num: "05",
    title: "Forecast Guardrails",
    question: "Why are forecasts sometimes labeled FORECAST WITHHELD?",
    shortDesc: "Enforces strict scientific integrity when Brier Skill Scores fail to meet positive predictive thresholds.",
    fullAnswer:
      "FlameSeek enforces scientific integrity: if LightGBM or persistence models do not achieve positive Brier Skill Scores over historical holdout validation for a given terrain and atmospheric regime, the forecast is withheld rather than presenting unreliable guesswork.",
    metric: "ZERO HALLUCINATION • INTEGRITY FIRST",
    accentColor: "#ff4d26",
    glowColor: "rgba(255, 77, 38, 0.55)",
    pinX: 965,
    pinY: 515,
    cardTopY: 35,
    cardBottomY: 175,
    tier: 1,
  },
];

export default function MethodologyRoadmap() {
  const [visibleStepCount, setVisibleStepCount] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [activeMilestoneId, setActiveMilestoneId] = useState<string>("four-witness");
  const containerRef = useRef<HTMLDivElement | null>(null);

  const totalSteps = ROADMAP_DATA.length;

  // Staggered sequential reveal animation
  useEffect(() => {
    if (!isPlaying) return;

    if (visibleStepCount < totalSteps) {
      const timer = setTimeout(() => {
        setVisibleStepCount((prev) => prev + 1);
      }, 650);
      return () => clearTimeout(timer);
    }
  }, [isPlaying, visibleStepCount, totalSteps]);

  const handleReplay = () => {
    setVisibleStepCount(0);
    setIsPlaying(true);
  };

  const selectMilestone = (id: string) => {
    setActiveMilestoneId(id);
  };

  const activeMilestone =
    ROADMAP_DATA.find((m) => m.id === activeMilestoneId) || ROADMAP_DATA[0];

  const activeIndex = ROADMAP_DATA.findIndex((m) => m.id === activeMilestone.id);

  const goToPrev = () => {
    const prevIdx = (activeIndex - 1 + totalSteps) % totalSteps;
    setActiveMilestoneId(ROADMAP_DATA[prevIdx].id);
  };

  const goToNext = () => {
    const nextIdx = (activeIndex + 1) % totalSteps;
    setActiveMilestoneId(ROADMAP_DATA[nextIdx].id);
  };

  return (
    <div className="roadmap-outer-wrapper" ref={containerRef}>
      {/* Top Controller Bar */}
      <div className="roadmap-controls-bar">
        <div className="roadmap-status-pill">
          <span className="roadmap-pulse-indicator" />
          <span>METHODOLOGY TIMELINE ROADMAP</span>
        </div>

        <div className="roadmap-action-btns">
          <button
            type="button"
            className="roadmap-btn roadmap-replay-btn"
            onClick={handleReplay}
            aria-label="Replay animated roadmap"
          >
            <RotateCcw size={14} />
            <span>Replay Roadmap</span>
          </button>

          <button
            type="button"
            className="roadmap-btn roadmap-toggle-all"
            onClick={() => setVisibleStepCount(totalSteps)}
            aria-label="Show all milestones"
          >
            <CheckCircle2 size={14} />
            <span>Show All ({totalSteps})</span>
          </button>
        </div>
      </div>

      {/* ====================================================================
          DESKTOP PERSPECTIVE WINDING ROADMAP STAGE (1200 x 720 Canvas)
          ==================================================================== */}
      <div className="roadmap-stage-desktop">
        <svg
          viewBox="0 0 1200 720"
          className="roadmap-svg-canvas"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            {/* Roadway Surface Gradient */}
            <linearGradient id="roadwayGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0a162b" stopOpacity="0.9" />
              <stop offset="50%" stopColor="#0e2140" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#142c54" stopOpacity="0.9" />
            </linearGradient>

            {/* Glowing Roadway Border */}
            <linearGradient id="roadCurbGlow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#00f2fe" stopOpacity="0.7" />
              <stop offset="50%" stopColor="#38bdf8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#00f2fe" stopOpacity="0.7" />
            </linearGradient>

            {/* Road Ground Shadow */}
            <filter id="roadShadow" x="-10%" y="-10%" width="130%" height="130%">
              <feDropShadow dx="0" dy="16" stdDeviation="18" floodColor="#000000" floodOpacity="0.95" />
            </filter>
          </defs>

          {/* Winding Perspective Road Surface */}
          <path
            d="M 10 470 
               C 45 475, 65 485, 85 490 
               C 145 515, 245 570, 305 570 
               C 375 570, 465 480, 525 480 
               C 585 480, 685 585, 745 585 
               C 815 585, 905 495, 965 495 
               C 1035 495, 1125 470, 1190 470 
               L 1190 550 
               C 1125 550, 1035 575, 965 575 
               C 905 575, 815 665, 745 665 
               C 685 665, 585 560, 525 560 
               C 465 560, 375 650, 305 650 
               C 245 650, 145 595, 85 570 
               C 65 565, 45 555, 10 550 Z"
            fill="url(#roadwayGradient)"
            stroke="url(#roadCurbGlow)"
            strokeWidth="2.5"
            filter="url(#roadShadow)"
            className="roadmap-surface-path"
          />

          {/* Roadway Centerline Dashed Lane */}
          <path
            d="M 10 510 
               C 45 515, 65 525, 85 530 
               C 145 555, 245 610, 305 610 
               C 375 610, 465 520, 525 520 
               C 585 520, 685 625, 745 625 
               C 815 625, 905 535, 965 535 
               C 1035 535, 1125 510, 1190 510"
            fill="none"
            stroke="rgba(0, 242, 254, 0.45)"
            strokeWidth="2.5"
            strokeDasharray="14 12"
            className="roadmap-lane-dashes"
          />

          {/* Render Milestone Pins, Ground Shadows, and Vertical Stem Lines */}
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const isSelected = activeMilestoneId === item.id;
            const pinTipY = item.pinY - 32;

            return (
              <g
                key={item.id}
                className={`roadmap-svg-node ${isVisible ? "node-visible" : "node-hidden"}`}
                style={{
                  transitionDelay: `${idx * 120}ms`,
                }}
              >
                {/* Oval Perspective Ground Shadow under Pin */}
                <ellipse
                  cx={item.pinX}
                  cy={item.pinY + 12}
                  rx="18"
                  ry="6"
                  fill="rgba(0, 0, 0, 0.75)"
                  className="roadmap-pin-shadow"
                />

                {/* Vertical Stem Line: 100% Precision Connection from Pin Tip to Card Bottom */}
                <line
                  x1={item.pinX}
                  y1={pinTipY}
                  x2={item.pinX}
                  y2={item.cardBottomY}
                  stroke={item.accentColor}
                  strokeWidth={isSelected ? "3" : "2"}
                  strokeDasharray="4 3"
                  className="roadmap-stem-line"
                  opacity={isSelected ? 1 : 0.75}
                />

                {/* Vertical Stem Glow Line */}
                <line
                  x1={item.pinX}
                  y1={pinTipY}
                  x2={item.pinX}
                  y2={item.cardBottomY}
                  stroke={item.accentColor}
                  strokeWidth="6"
                  opacity={isSelected ? "0.4" : "0.15"}
                  className="roadmap-stem-glow"
                />

                {/* Map Pin Marker (Pin-drop shape from video reference) */}
                <g
                  transform={`translate(${item.pinX - 16}, ${item.pinY - 32})`}
                  className={`roadmap-pin-marker ${isSelected ? "pin-selected" : ""}`}
                  onClick={() => selectMilestone(item.id)}
                  style={{ cursor: "pointer" }}
                >
                  {/* Pin Drop Outer Path */}
                  <path
                    d="M 16 0 C 7.2 0, 0 7.2, 0 16 C 0 28, 16 34, 16 34 C 16 34, 32 28, 32 16 C 32 7.2, 24.8 0, 16 0 Z"
                    fill={item.accentColor}
                    stroke="#ffffff"
                    strokeWidth="1.5"
                    filter="drop-shadow(0 4px 8px rgba(0,0,0,0.65))"
                  />
                  {/* Pin Inner Hole Circle */}
                  <circle cx="16" cy="14" r="5" fill="#030712" />
                </g>
              </g>
            );
          })}
        </svg>

        {/* ====================================================================
            NON-OVERLAPPING STAGGERED MILESTONE CARDS (Two-Tier Spatial Layout)
            ==================================================================== */}
        <div className="roadmap-cards-layer">
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const isSelected = activeMilestoneId === item.id;

            // Mathematical percentage coordinates within 1200 x 720 canvas
            // Left offset starts at pinX - 22px so the badge center is at pinX
            const cardLeftPercent = ((item.pinX - 22) / 1200) * 100;
            const cardTopPercent = (item.cardTopY / 720) * 100;

            return (
              <div
                key={item.id}
                className={`roadmap-card-anchor ${isVisible ? "card-visible" : "card-hidden"} ${
                  isSelected ? "card-selected" : ""
                } tier-${item.tier}`}
                style={{
                  top: `${cardTopPercent}%`,
                  left: `${cardLeftPercent}%`,
                  transitionDelay: `${idx * 140 + 160}ms`,
                  "--item-accent": item.accentColor,
                  "--item-glow": item.glowColor,
                } as React.CSSProperties}
              >
                {/* Milestone Pill Card */}
                <div
                  className="roadmap-card-pill"
                  onClick={() => selectMilestone(item.id)}
                  role="button"
                  tabIndex={0}
                  aria-selected={isSelected}
                >
                  {/* Card Top Row: Circular Number Badge + Metric Tag */}
                  <div className="roadmap-card-header-row">
                    <div className="roadmap-badge-circle">
                      <span className="roadmap-badge-num">{item.num}</span>
                    </div>
                    <span className="roadmap-metric-tag">{item.metric.split("•")[0]}</span>
                  </div>

                  {/* Card Title & Concise Summary */}
                  <div className="roadmap-pill-body">
                    <h4 className="roadmap-milestone-title">{item.title}</h4>
                    <p className="roadmap-short-desc">{item.shortDesc}</p>

                    <div className="roadmap-inspect-action">
                      <span>{isSelected ? "Inspecting Standard" : "Inspect Methodology"}</span>
                      <ChevronRight size={13} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ====================================================================
          ACTIVE SCIENTIFIC METHODOLOGY INSPECTOR PANEL
          ==================================================================== */}
      <div
        className="roadmap-inspector-panel"
        style={{
          "--item-accent": activeMilestone.accentColor,
          "--item-glow": activeMilestone.glowColor,
        } as React.CSSProperties}
      >
        <div className="inspector-top-row">
          <div className="inspector-badge-group">
            <span className="inspector-step-tag">MILESTONE {activeMilestone.num}</span>
            <span className="inspector-metric-tag">{activeMilestone.metric}</span>
          </div>

          <div className="inspector-nav-group">
            <button
              type="button"
              className="inspector-nav-btn"
              onClick={goToPrev}
              aria-label="Previous methodology step"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="inspector-step-counter">
              {activeMilestone.num} / {String(totalSteps).padStart(2, "0")}
            </span>
            <button
              type="button"
              className="inspector-nav-btn"
              onClick={goToNext}
              aria-label="Next methodology step"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        <h3 className="inspector-title">{activeMilestone.title}</h3>
        <p className="inspector-question">{activeMilestone.question}</p>

        <div className="inspector-body-box">
          <p className="inspector-full-answer">{activeMilestone.fullAnswer}</p>

          <div className="inspector-footer">
            <span className="inspector-verified-tag">
              <ShieldCheck size={14} />
              Peer-Reviewed Observation Architecture // Zero Proprietary Black-Boxes
            </span>
          </div>
        </div>
      </div>

      {/* ====================================================================
          MOBILE & TABLET ADAPTIVE VERTICAL ROADMAP (< 980px)
          ==================================================================== */}
      <div className="roadmap-stage-mobile">
        <div className="roadmap-mobile-track">
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const isSelected = activeMilestoneId === item.id;

            return (
              <div
                key={item.id}
                className={`roadmap-mobile-step ${isVisible ? "mobile-visible" : "mobile-hidden"}`}
                style={{
                  "--item-accent": item.accentColor,
                  "--item-glow": item.glowColor,
                } as React.CSSProperties}
              >
                {/* Mobile Pin & Timeline Bar */}
                <div className="roadmap-mobile-left">
                  <div className="roadmap-mobile-pin">
                    <span>{item.num}</span>
                  </div>
                  {idx < totalSteps - 1 && <div className="roadmap-mobile-line" />}
                </div>

                {/* Mobile Card */}
                <div
                  className={`roadmap-mobile-card ${isSelected ? "expanded" : ""}`}
                  onClick={() => selectMilestone(item.id)}
                >
                  <div className="roadmap-mobile-card-top">
                    <span className="roadmap-metric-tag">{item.metric}</span>
                    <span className="roadmap-mobile-num">STAGE {item.num}</span>
                  </div>

                  <h4 className="roadmap-milestone-title">{item.title}</h4>
                  <p className="roadmap-milestone-question">{item.question}</p>

                  <div className="roadmap-mobile-desc">
                    {isSelected ? (
                      <p>{item.fullAnswer}</p>
                    ) : (
                      <p>{item.shortDesc}</p>
                    )}
                  </div>

                  <div className="roadmap-mobile-actions">
                    <span className="roadmap-toggle-text">
                      {isSelected ? "Viewing Full Proof" : "Read Scientific Proof"}
                    </span>
                    <ChevronRight size={14} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bottom Summary Legend */}
      <div className="roadmap-footer-legend">
        {ROADMAP_DATA.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`roadmap-legend-item ${activeMilestoneId === item.id ? "active" : ""}`}
            onClick={() => selectMilestone(item.id)}
          >
            <span className="legend-dot" style={{ background: item.accentColor }} />
            <span>{item.num} {item.title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
