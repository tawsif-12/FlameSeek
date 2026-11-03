import React, { useState, useEffect, useRef, useCallback } from "react";
import "./satellite-carousel.css";
import { Link } from "react-router-dom";
import {
  Satellite,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  Compass,
  Cpu,
  Eye,
  Activity,
  Flame,
  Radio,
} from "lucide-react";

export interface SatelliteItem {
  id: string;
  num: string;
  name: string;
  agency: string;
  tagline: string;
  image: string;
  sensor: string;
  orbit: string;
  overpass: string;
  swath: string;
  resolution: string;
  role: string;
  baseline: string;
  accentColor: string;
  glowColor: string;
}

export const SATELLITES_DATA: SatelliteItem[] = [
  {
    id: "terra",
    num: "01",
    name: "TERRA",
    agency: "NASA EOS AM-1",
    tagline: "Morning Thermal Baseline & 26-Year Climate Record",
    image: "/satellites/terra.jpg",
    sensor: "MODIS Payload (36 Bands)",
    orbit: "705 km Polar Sun-Sync",
    overpass: "10:30 AM (Descending)",
    swath: "2,330 km",
    resolution: "1,000 m Nadir",
    baseline: "2000 to Present (26 Yrs)",
    role: "Detects pre-burn thermal buildup before midday cloud & storm formation. Anchor of the 26-year unbroken climate series.",
    accentColor: "#38bdf8",
    glowColor: "rgba(56, 189, 248, 0.5)",
  },
  {
    id: "aqua",
    num: "02",
    name: "AQUA",
    agency: "NASA EOS PM-1",
    tagline: "Diurnal Peak Fire Power Reference Anchor",
    image: "/satellites/aqua.jpg",
    sensor: "MODIS Payload (36 Bands)",
    orbit: "705 km Polar Sun-Sync",
    overpass: "01:30 PM (Ascending)",
    swath: "2,330 km",
    resolution: "1,000 m Nadir",
    baseline: "Aqua 13:30 Eqv Anchor",
    role: "Observes during daily peak ambient temperature and fire intensity. Standard reference for diurnal solar power harmonization.",
    accentColor: "#00f2fe",
    glowColor: "rgba(0, 242, 254, 0.55)",
  },
  {
    id: "snpp",
    num: "03",
    name: "SUOMI NPP",
    agency: "NASA / NOAA",
    tagline: "High-Resolution 375m Sub-Pixel Thermal Precision",
    image: "/satellites/suomi-npp.jpg",
    sensor: "VIIRS Instrument (22 Channels)",
    orbit: "824 km Polar Sun-Sync",
    overpass: "01:30 PM / 01:30 AM",
    swath: "3,040 km (Zero-Gap)",
    resolution: "375 m I-Band Nadir",
    baseline: "Active Since 2012",
    role: "High-resolution fire perimeter mapping and sub-pixel thermal sensitivity from nadir to edge. Day/Night Band detects nocturnal fires.",
    accentColor: "#22c55e",
    glowColor: "rgba(34, 197, 94, 0.5)",
  },
  {
    id: "noaa20",
    num: "04",
    name: "NOAA-20",
    agency: "JPSS-1, NOAA",
    tagline: "50-Minute Temporal Persistence Verifier",
    image: "/satellites/noaa-20.jpg",
    sensor: "VIIRS Instrument (22 Channels)",
    orbit: "824 km Polar Sun-Sync",
    overpass: "02:20 PM (50 min offset)",
    swath: "3,040 km (Zero-Gap)",
    resolution: "375 m I-Band Nadir",
    baseline: "Active Since 2018",
    role: "Trailing Suomi NPP by 50 minutes, NOAA-20 confirms active fire persistence vs transient glint. Powers the Hide-One-Witness test.",
    accentColor: "#ff8a5b",
    glowColor: "rgba(255, 138, 91, 0.55)",
  },
];

interface Satellite3DCoverflowProps {
  onSatelliteChange?: (satId: "terra" | "aqua" | "snpp" | "noaa20") => void;
}

export default function Satellite3DCoverflow({ onSatelliteChange }: Satellite3DCoverflowProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [hasFocus, setHasFocus] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const total = SATELLITES_DATA.length;

  const goToNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % total);
  }, [total]);

  const goToPrev = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + total) % total);
  }, [total]);

  const selectIndex = (idx: number) => {
    setCurrentIndex(idx);
  };

  // Sync with parent when satellite changes
  useEffect(() => {
    const currentSat = SATELLITES_DATA[currentIndex];
    if (onSatelliteChange && currentSat) {
      onSatelliteChange(currentSat.id as any);
    }
  }, [currentIndex, onSatelliteChange]);

  // Bring the left-hand card into the spotlight so autoplay travels left to right.
  useEffect(() => {
    if (isPaused || hasFocus || reducedMotion) return;
    const timer = setInterval(() => {
      goToPrev();
    }, 4200);
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

  // Calculate shortest circular offset between indices
  const getOffset = (idx: number): number => {
    let diff = idx - currentIndex;
    if (diff > total / 2) diff -= total;
    if (diff < -total / 2) diff += total;
    return diff;
  };

  // Four original records form a circular strip; mirror only the opposite outer
  // record to fill five desktop positions without inventing satellite data.
  const cards = SATELLITES_DATA.map((sat, idx) => ({ sat, idx, offset: getOffset(idx), key: sat.id }));
  const opposite = cards.find((card) => Math.abs(card.offset) === 2);
  if (opposite) cards.push({ ...opposite, offset: -opposite.offset, key: `${opposite.sat.id}-wrap` });

  return (
    <div
      className="sat-coverflow-wrapper"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onFocusCapture={() => setHasFocus(true)}
      onBlurCapture={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHasFocus(false); }}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      ref={containerRef}
      role="region"
      aria-label="Satellite constellation carousel"
      aria-roledescription="carousel"
    >
      {/* 3D Perspective Stage */}
      <div className="sat-coverflow-stage">
        {cards.map(({ sat, idx, offset, key }) => {
          const isCenter = offset === 0;
          const level = Math.abs(offset);

          return (
            <div
              key={key}
              className={`sat-3d-card ${isCenter ? "active-center" : "flanking-card"}`}
              data-offset={offset}
              data-level={level}
              aria-current={isCenter ? "true" : undefined}
              style={{ "--card-offset": offset, "--card-direction": Math.sign(offset), "--sat-accent": sat.accentColor, "--sat-glow": sat.glowColor, zIndex: 10 - level } as React.CSSProperties}
              onClick={() => selectIndex(idx)}
              role="group"
              tabIndex={isCenter || level === 1 ? 0 : -1}
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectIndex(idx); }
                if (e.key === "ArrowLeft") { e.preventDefault(); goToPrev(); }
                if (e.key === "ArrowRight") { e.preventDefault(); goToNext(); }
              }}
              aria-label={`Select ${sat.name} satellite`}
            >
              {/* Card Image Background */}
              <div className="sat-card-media">
                <img
                  src={sat.image}
                  alt={`${sat.name} in orbit`}
                  className="sat-card-img"
                  loading="lazy"
                />
                <div className="sat-card-gradient-top" />
                <div className="sat-card-gradient-bottom" />
                <div className="sat-card-image-caption">
                  <div className="sat-card-agency">{sat.agency}</div>
                  <h3 className="sat-card-name">{sat.name}</h3>
                </div>
              </div>

              {/* Card Header Overlay */}
              <div className="sat-card-header">
                <span className="sat-card-badge">
                  <span
                    className="sat-badge-pulse"
                    style={{ background: sat.accentColor, boxShadow: `0 0 10px ${sat.accentColor}` }}
                  />
                  <span>{sat.overpass}</span>
                </span>
                <span className="sat-card-sensor-pill">{sat.sensor.split(" ")[0]}</span>
              </div>

              {/* Card Content & Telemetry Footer */}
              <div className="sat-card-footer">
                <div className="sat-card-tagline">{sat.tagline}</div>

                <div className="sat-card-specs-grid">
                  <div className="sat-spec-col">
                    <span className="sat-spec-lbl">SWATH</span>
                    <strong className="sat-spec-val">{sat.swath}</strong>
                  </div>
                  <div className="sat-spec-col">
                    <span className="sat-spec-lbl">RESOLUTION</span>
                    <strong className="sat-spec-val">{sat.resolution}</strong>
                  </div>
                  <div className="sat-spec-col">
                    <span className="sat-spec-lbl">ORBIT</span>
                    <strong className="sat-spec-val">{sat.orbit.split(" ")[0]}</strong>
                  </div>
                </div>

                <p className="sat-card-desc" title={sat.role}>{sat.role}</p>

                {isCenter && (
                  <div className="sat-card-cta-row">
                    <Link
                      to="/fire-map"
                      className="sat-card-cta-btn"
                      onClick={(e) => e.stopPropagation()}
                      tabIndex={isCenter ? 0 : -1}
                    >
                      <span>Explore Live Orbit</span>
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
        className="sat-nav-arrow sat-arrow-left"
        onClick={goToPrev}
        aria-label="Previous satellite"
      >
        <ChevronLeft size={24} />
      </button>

      <button
        type="button"
        className="sat-nav-arrow sat-arrow-right"
        onClick={goToNext}
        aria-label="Next satellite"
      >
        <ChevronRight size={24} />
      </button>

      {/* Indicator Pill Dots */}
      <div className="sat-indicators-bar" aria-label="Choose satellite">
        {SATELLITES_DATA.map((sat, idx) => (
          <button
            key={sat.id}
            type="button"
            className={`sat-indicator-pill ${currentIndex === idx ? "active" : ""}`}
            onClick={() => selectIndex(idx)}
            aria-pressed={currentIndex === idx}
            aria-label={`Jump to ${sat.name}`}
          >
            <span className="sat-pill-num">{sat.num}</span>
            <span className="sat-pill-name">{sat.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

