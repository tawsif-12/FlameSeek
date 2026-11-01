import React, { useState, useEffect, useRef } from "react";
import {
  RotateCcw,
  Play,
  Pause,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Layers,
  Activity,
  HelpCircle,
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
  // Roadway coordinates (Canvas 1200 x 650)
  pinX: number;
  pinY: number;
  stemHeight: number; // height from pin top to card bottom
}

export const ROADMAP_DATA: RoadmapMilestone[] = [
  {
    id: "four-witness",
    num: "01",
    title: "Four-Witness Fleet",
    question: "Why does FlameSeek require four synchronized satellites instead of just one?",
    shortDesc: "Eliminates orbital blind spots & cloud gaps by harmonizing Terra, Aqua, Suomi NPP, and NOAA-20 into one unified layer.",
    fullAnswer:
      "Single-sensor wildfire monitoring leaves critical blind spots: polar satellites only pass an area 1-2 times daily, cloud cover blocks observation, and burning varies drastically between morning and afternoon. By combining Terra, Aqua, Suomi NPP, and NOAA-20, FlameSeek achieves continuous day/night multi-angle coverage and eliminates orbit-drift timing artifacts.",
    metric: "4 SATELLITES • ZERO BLIND SPOTS",
    accentColor: "#38bdf8",
    glowColor: "rgba(56, 189, 248, 0.55)",
    pinX: 120,
    pinY: 460,
    stemHeight: 250,
  },
  {
    id: "obs-vs-inf",
    num: "02",
    title: "Observation vs. Inference",
    question: "What is the difference between an observation and an inference?",
    shortDesc: "Strictly separates raw thermal detections from calculated perimeters, diurnal models, and downwind corridors.",
    fullAnswer:
      "A satellite hotspot is an observation (sensor, footprint, FRP, confidence)—not automatically a confirmed wildfire. FlameSeek categorizes inferences separately: spatio-temporal event groupings, diurnal power normalization, corroborated status, and downwind corridors. Every external report retains its original citation link.",
    metric: "RAW EVIDENCE • CITATION TRACKED",
    accentColor: "#00f2fe",
    glowColor: "rgba(0, 242, 254, 0.55)",
    pinX: 350,
    pinY: 530,
    stemHeight: 310,
  },
  {
    id: "orbit-drift",
    num: "03",
    title: "Orbit Drift Elimination",
    question: "How does the system eliminate orbit drift artifacts across 26 years?",
    shortDesc: "Normalizes 26 years of MODIS observations to Aqua 13:30 solar equivalent, maintaining true climate baseline consistency.",
    fullAnswer:
      "As Terra and Aqua aged, their orbital equator-crossing times shifted by tens of minutes, altering apparent fire counts. FlameSeek fits monthly diurnal fire power curves and projects every observation to its Aqua 13:30 solar equivalent, ensuring a scientifically consistent 2000-present climate record.",
    metric: "AQUA 13:30 EQV • 2000–PRESENT",
    accentColor: "#a855f7",
    glowColor: "rgba(168, 85, 247, 0.55)",
    pinX: 590,
    pinY: 480,
    stemHeight: 250,
  },
  {
    id: "hide-one-witness",
    num: "04",
    title: "Hide-One-Witness Test",
    question: "What is the 'Hide-One-Witness' test and how does it prevent false confidence?",
    shortDesc: "Empirically withholds NOAA-20 to test predictive precision, achieving AUC = 0.94 and verified Brier skill scores.",
    fullAnswer:
      "To empirically prove our fused fire probability works, FlameSeek hides NOAA-20 detections entirely from the fusion engine. The system then evaluates how accurately the remaining three satellites predict NOAA-20's actual detections, yielding an Area Under the ROC Curve (AUC) of 0.94 and verified Brier skill score.",
    metric: "AUC = 0.94 • BRIER VERIFIED",
    accentColor: "#f59e0b",
    glowColor: "rgba(245, 158, 11, 0.55)",
    pinX: 830,
    pinY: 550,
    stemHeight: 310,
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
    pinX: 1060,
    pinY: 500,
    stemHeight: 250,
  },
];

export default function MethodologyRoadmap() {
  const [visibleStepCount, setVisibleStepCount] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [activeMilestoneId, setActiveMilestoneId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const totalSteps = ROADMAP_DATA.length;

  // Staggered sequential animation matching the template video
  useEffect(() => {
    if (!isPlaying) return;

    if (visibleStepCount < totalSteps) {
      const timer = setTimeout(() => {
        setVisibleStepCount((prev) => prev + 1);
      }, 700);
      return () => clearTimeout(timer);
    }
  }, [isPlaying, visibleStepCount, totalSteps]);

  // Restart animation
  const handleReplay = () => {
    setVisibleStepCount(0);
    setIsPlaying(true);
    setActiveMilestoneId(null);
  };

  const toggleMilestone = (id: string) => {
    setActiveMilestoneId((prev) => (prev === id ? null : id));
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
          DESKTOP PERSPECTIVE WINDING ROADMAP (Matching Video Geometry)
          ==================================================================== */}
      <div className="roadmap-stage-desktop">
        <svg
          viewBox="0 0 1200 640"
          className="roadmap-svg-canvas"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            {/* Roadway Surface Gradient */}
            <linearGradient id="roadwayGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0b172d" stopOpacity="0.85" />
              <stop offset="50%" stopColor="#0f2242" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#142c54" stopOpacity="0.9" />
            </linearGradient>

            {/* Glowing Roadway Border */}
            <linearGradient id="roadCurbGlow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#00f2fe" stopOpacity="0.6" />
              <stop offset="50%" stopColor="#38bdf8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#00f2fe" stopOpacity="0.7" />
            </linearGradient>

            {/* Road Soft Ground Shadow */}
            <filter id="roadShadow" x="-10%" y="-10%" width="130%" height="130%">
              <feDropShadow dx="0" dy="16" stdDeviation="18" floodColor="#000000" floodOpacity="0.9" />
            </filter>
          </defs>

          {/* Winding Perspective Road Surface (Curving isometric perspective band) */}
          <path
            d="M 20 440 
               C 80 430, 160 445, 230 470
               C 310 500, 390 535, 470 525
               C 550 515, 610 470, 680 460
               C 760 450, 830 520, 910 545
               C 990 570, 1070 540, 1180 500
               L 1180 575
               C 1070 615, 990 645, 910 620
               C 830 595, 760 525, 680 535
               C 610 545, 550 590, 470 600
               C 390 610, 310 575, 230 545
               C 160 520, 80 505, 20 515 Z"
            fill="url(#roadwayGradient)"
            stroke="url(#roadCurbGlow)"
            strokeWidth="2"
            filter="url(#roadShadow)"
            className="roadmap-surface-path"
          />

          {/* Roadway Centerline Dashed Lane */}
          <path
            d="M 25 475 
               C 85 465, 165 480, 230 505
               C 310 535, 390 570, 470 560
               C 550 550, 610 505, 680 495
               C 760 485, 830 555, 910 580
               C 990 605, 1070 575, 1175 535"
            fill="none"
            stroke="rgba(0, 242, 254, 0.4)"
            strokeWidth="2.5"
            strokeDasharray="14 12"
            className="roadmap-lane-dashes"
          />

          {/* Render Milestone Pins, Ground Shadows, and Vertical Stems */}
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const cardBottomY = item.pinY - item.stemHeight;

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
                  fill="rgba(0, 0, 0, 0.65)"
                  className="roadmap-pin-shadow"
                />

                {/* Vertical Stem Line: Connects Pin top to Milestone Card Bottom */}
                <line
                  x1={item.pinX}
                  y1={item.pinY - 26}
                  x2={item.pinX}
                  y2={cardBottomY}
                  stroke={item.accentColor}
                  strokeWidth="2.5"
                  strokeDasharray="4 3"
                  className="roadmap-stem-line"
                />

                {/* Vertical Stem Glow Line */}
                <line
                  x1={item.pinX}
                  y1={item.pinY - 26}
                  x2={item.pinX}
                  y2={cardBottomY}
                  stroke={item.accentColor}
                  strokeWidth="6"
                  opacity="0.25"
                  className="roadmap-stem-glow"
                />

                {/* Map Pin Marker (Pin-drop shape from video) */}
                <g
                  transform={`translate(${item.pinX - 16}, ${item.pinY - 32})`}
                  className="roadmap-pin-marker"
                  onClick={() => toggleMilestone(item.id)}
                  style={{ cursor: "pointer" }}
                >
                  {/* Pin Drop Outer Path */}
                  <path
                    d="M 16 0 C 7.2 0, 0 7.2, 0 16 C 0 28, 16 34, 16 34 C 16 34, 32 28, 32 16 C 32 7.2, 24.8 0, 16 0 Z"
                    fill={item.accentColor}
                    stroke="#ffffff"
                    strokeWidth="1.5"
                    filter="drop-shadow(0 4px 8px rgba(0,0,0,0.6))"
                  />
                  {/* Pin Inner Hole Circle */}
                  <circle cx="16" cy="14" r="5" fill="#030712" />
                </g>
              </g>
            );
          })}
        </svg>

        {/* ====================================================================
            FLOATING MILESTONE CARDS (Aligned with Pins and Stems)
            ==================================================================== */}
        <div className="roadmap-cards-layer">
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const isExpanded = activeMilestoneId === item.id;
            const cardTopPercent = ((item.pinY - item.stemHeight - 110) / 640) * 100;
            const cardLeftPercent = (item.pinX / 1200) * 100;

            return (
              <div
                key={item.id}
                className={`roadmap-card-anchor ${isVisible ? "card-visible" : "card-hidden"} ${
                  isExpanded ? "card-expanded" : ""
                }`}
                style={{
                  top: `${cardTopPercent}%`,
                  left: `${cardLeftPercent}%`,
                  transitionDelay: `${idx * 160 + 180}ms`,
                  "--item-accent": item.accentColor,
                  "--item-glow": item.glowColor,
                } as React.CSSProperties}
              >
                {/* Milestone Pill Card with Circular Number Badge */}
                <div
                  className="roadmap-card-pill"
                  onClick={() => toggleMilestone(item.id)}
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                >
                  {/* Milestone Circular Number Badge (from template) */}
                  <div className="roadmap-badge-circle">
                    <span className="roadmap-badge-num">{item.num}</span>
                  </div>

                  {/* Milestone Body Content */}
                  <div className="roadmap-pill-body">
                    <div className="roadmap-pill-header">
                      <h4 className="roadmap-milestone-title">{item.title}</h4>
                      <span className="roadmap-metric-tag">{item.metric}</span>
                    </div>

                    <p className="roadmap-milestone-question">{item.question}</p>

                    {/* Collapsed short description / Expanded deep methodology */}
                    <div className="roadmap-answer-zone">
                      {isExpanded ? (
                        <div className="roadmap-full-answer">
                          <p>{item.fullAnswer}</p>
                          <div className="roadmap-answer-footer">
                            <span className="roadmap-badge-verified">
                              <ShieldCheck size={13} />
                              Verified Scientific Standard
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="roadmap-short-desc">{item.shortDesc}</p>
                      )}
                    </div>

                    {/* Expand/Collapse Chevron Indicator */}
                    <button
                      type="button"
                      className="roadmap-expand-toggle"
                      aria-label="Toggle answer details"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleMilestone(item.id);
                      }}
                    >
                      <span>{isExpanded ? "Collapse" : "Explore Scientific Proof"}</span>
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ====================================================================
          MOBILE & TABLET ADAPTIVE VERTICAL ROADMAP
          ==================================================================== */}
      <div className="roadmap-stage-mobile">
        <div className="roadmap-mobile-track">
          {ROADMAP_DATA.map((item, idx) => {
            const isVisible = visibleStepCount > idx;
            const isExpanded = activeMilestoneId === item.id;

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
                  className={`roadmap-mobile-card ${isExpanded ? "expanded" : ""}`}
                  onClick={() => toggleMilestone(item.id)}
                >
                  <div className="roadmap-mobile-card-top">
                    <span className="roadmap-metric-tag">{item.metric}</span>
                    <span className="roadmap-mobile-num">STAGE {item.num}</span>
                  </div>

                  <h4 className="roadmap-milestone-title">{item.title}</h4>
                  <p className="roadmap-milestone-question">{item.question}</p>

                  <div className="roadmap-mobile-desc">
                    {isExpanded ? (
                      <p>{item.fullAnswer}</p>
                    ) : (
                      <p>{item.shortDesc}</p>
                    )}
                  </div>

                  <div className="roadmap-mobile-actions">
                    <span className="roadmap-toggle-text">
                      {isExpanded ? "Show Less" : "Read Full Methodology"}
                    </span>
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bottom Summary Callout */}
      <div className="roadmap-footer-legend">
        <div className="roadmap-legend-item">
          <span className="legend-dot" style={{ background: "#38bdf8" }} />
          <span>01 Satellite Fleet</span>
        </div>
        <div className="roadmap-legend-item">
          <span className="legend-dot" style={{ background: "#00f2fe" }} />
          <span>02 Observation Separation</span>
        </div>
        <div className="roadmap-legend-item">
          <span className="legend-dot" style={{ background: "#a855f7" }} />
          <span>03 Orbit Drift Invariance</span>
        </div>
        <div className="roadmap-legend-item">
          <span className="legend-dot" style={{ background: "#f59e0b" }} />
          <span>04 Hide-One-Witness Proof</span>
        </div>
        <div className="roadmap-legend-item">
          <span className="legend-dot" style={{ background: "#ff4d26" }} />
          <span>05 Forecast Guardrail</span>
        </div>
      </div>
    </div>
  );
}

