import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "react-plotly.js";
import {
  Satellite,
  Radio,
  Flame,
  ArrowRight,
  ChevronRight,
  Crosshair,
  ShieldAlert,
  Layers,
  Activity,
  Compass,
  Clock,
  Cpu,
  Eye,
  Radar,
  Globe2,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Plus,
  Minus,
} from "lucide-react";
import { getCurrentHotspots, getEvents } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";
import type { FireEventSummary, HotspotRecord } from "../types/api";
import OutcrowdEarthSatellite from "../components/OutcrowdEarthSatellite";
import Satellite3DCoverflow from "../components/Satellite3DCoverflow";
import Pipeline3DTransition from "../components/Pipeline3DTransition";
import MethodologyRoadmap from "../components/MethodologyRoadmap";
import "../outcrowd-satellite.css";
import HarmonizedRecordSection from "../components/HarmonizedRecordSection";

type SensorCounts = Record<"modis" | "viirs_snpp" | "viirs_noaa20" | "viirs_noaa21", number>;

const EMPTY_COUNTS: SensorCounts = { modis: 0, viirs_snpp: 0, viirs_noaa20: 0, viirs_noaa21: 0 };
const SENSOR_LABELS = ["MODIS (Terra/Aqua)", "S-NPP (VIIRS)", "NOAA-20 (VIIRS)", "NOAA-21 (VIIRS)"];

const SATELLITE_FLEET = [
  {
    id: "terra",
    num: "01",
    name: "Terra MODIS",
    kicker: "NASA EOS AM-1 // MORNING WITNESS",
    sensor: "MODIS Payload (36 Bands)",
    orbit: "705 km Polar Sun-Synchronous",
    overpass: "10:30 AM LST (Descending)",
    swath: "2,330 km",
    resolution: "1,000 m Nadir",
    baseline: "26 Years",
    tagline: "Morning Thermal Baseline & 26-Year Climate Record",
    description:
      "Operating in polar sun-synchronous orbit since December 1999, Terra's MODIS payload establishes the morning observation anchor at 10:30 AM local solar time. By imaging the planet before afternoon convective cloud formation and thunderstorm obscuration, Terra captures early diurnal fire spread and provides the unbroken 26-year historical baseline from 2000 to present.",
    stats: [
      { num: "2,330", unit: "KM", label: "Swath Width" },
      { num: "1,000", unit: "M", label: "Nadir Resolution" },
      { num: "26", unit: "YRS", label: "Consistent Record" },
    ],
    status: "ONLINE // SYNCHRONIZED",
    route: "/fire-map",
  },
  {
    id: "aqua",
    num: "02",
    name: "Aqua MODIS",
    kicker: "NASA EOS PM-1 // AFTERNOON PEAK ANCHOR",
    sensor: "MODIS Payload (36 Bands)",
    orbit: "705 km Polar Sun-Synchronous",
    overpass: "01:30 PM LST (Ascending)",
    swath: "2,330 km",
    resolution: "1,000 m Nadir",
    baseline: "Aqua 13:30 Eqv",
    tagline: "Diurnal Peak Fire Power Anchor & Harmonization Standard",
    description:
      "Aqua crosses the equator at 1:30 PM local solar time during daily peak ambient temperature and maximum convective wildfire intensity. To eliminate orbit-drift artifacts and make observations comparable across decades, FlameSeek normalizes every satellite pass to its Aqua 13:30 solar equivalent using our Four-Witness diurnal conversion model.",
    stats: [
      { num: "13:30", unit: "LST", label: "Solar Diurnal Anchor" },
      { num: "4.3", unit: "MW", label: "50% Nadir Threshold" },
      { num: "36", unit: "BND", label: "Spectral Channels" },
    ],
    status: "ONLINE // SYNCHRONIZED",
    route: "/data-sources",
  },
  {
    id: "snpp",
    num: "03",
    name: "Suomi NPP VIIRS",
    kicker: "NASA / NOAA // HIGH-RESOLUTION PRECISION",
    sensor: "VIIRS Instrument (22 Channels)",
    orbit: "824 km Polar Sun-Synchronous",
    overpass: "01:30 PM / 01:30 AM",
    swath: "3,040 km (Zero-Gap)",
    resolution: "375 m I-Band Nadir",
    baseline: "Since 2012",
    tagline: "Sub-Pixel Thermal Resolution & 375m Edge-to-Edge Fidelity",
    description:
      "Launched in 2012, Suomi NPP's VIIRS instrument delivers 375m imagery—resolving active fires with 7x smaller pixel area than MODIS. Its aggregation algorithm maintains 375m spatial fidelity from nadir all the way to scan edge with zero equator gaps, while its panchromatic Day/Night Band detects nocturnal active fire fronts and differentiates gas flares from wildfires.",
    stats: [
      { num: "375", unit: "M", label: "I-Band Resolution" },
      { num: "3,040", unit: "KM", label: "Zero-Gap Swath" },
      { num: "24", unit: "H", label: "Day & Night Passes" },
    ],
    status: "ONLINE // SYNCHRONIZED",
    route: "/fire-map",
  },
  {
    id: "noaa20",
    num: "04",
    name: "NOAA-20 VIIRS",
    kicker: "JPSS-1, NOAA // TEMPORAL PERSISTENCE VERIFIER",
    sensor: "VIIRS Instrument (22 Channels)",
    orbit: "824 km Polar Sun-Synchronous",
    overpass: "02:20 PM (50 Min Offset)",
    swath: "3,040 km (Zero-Gap)",
    resolution: "375 m I-Band Nadir",
    baseline: "Since 2018",
    tagline: "Cross-Verification Witness & Predictive Validation Standard",
    description:
      "Trailing Suomi NPP by precisely 50 minutes in the identical orbital track, NOAA-20 provides definitive cross-sensor verification. It confirms whether thermal hotspots represent persistent active combustion versus transient sun glint or hot metal roofs. It powers FlameSeek's 'Hide-One-Witness' test, achieving an AUC of 0.94 and Brier skill score validation.",
    stats: [
      { num: "50", unit: "MIN", label: "Temporal Offset" },
      { num: "0.94", unit: "AUC", label: "Prediction ROC Score" },
      { num: "3,040", unit: "KM", label: "Swath Coverage" },
    ],
    status: "ONLINE // SYNCHRONIZED",
    route: "/fire-map",
  },
] as const;

const PARTNER_ORGANIZATIONS = [
  { name: "NASA FIRMS", role: "Active Fire System" },
  { name: "NOAA NESDIS", role: "Geostationary & Polar" },
  { name: "ESA Copernicus", role: "Sentinel-2 & EFFIS" },
  { name: "Skyfield & CelesTrak", role: "Orbital TLE Propagation" },
  { name: "WorldPop UN", role: "100m Population Density" },
  { name: "OpenStreetMap", role: "Infrastructure & Roads" },
  { name: "GDELT Project", role: "Global NLP News Event" },
  { name: "NIFC WFIGS", role: "National Incident Data" },
];

function formatAge(date: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 60000));
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`;
}

export default function HomePage() {
  const [hotspots, setHotspots] = useState<HotspotRecord[]>([]);
  const [events, setEvents] = useState<FireEventSummary[]>([]);
  const [counts, setCounts] = useState<SensorCounts>(EMPTY_COUNTS);
  const [totalDetections, setTotalDetections] = useState<number | null>(null);
  const [sourceMode, setSourceMode] = useState<"live" | "cached" | "demo" | "unavailable">("live");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [activeSat, setActiveSat] = useState<"terra" | "aqua" | "snpp" | "noaa20">("terra");

  useEffect(() => {
    let cancelled = false;
    const loadHotspots = async () => {
      try {
        return { response: await getCurrentHotspots(DEFAULT_SENSORS, 1, 600, undefined, false), usedDemo: false };
      } catch {
        return { response: await getCurrentHotspots(DEFAULT_SENSORS, 1, 600, undefined, true), usedDemo: true };
      }
    };
    const loadEvents = async () => {
      try {
        return await getEvents(2, 40, false);
      } catch {
        return await getEvents(2, 40, true);
      }
    };

    Promise.allSettled([loadHotspots(), loadEvents()]).then(([hotspotResult, eventResult]) => {
      if (cancelled) return;

      if (hotspotResult.status === "fulfilled") {
        const { response, usedDemo } = hotspotResult.value;
        const bySensor = (response.metadata.filtered_by_sensor ?? response.metadata.returned_by_sensor ?? {}) as Record<string, number>;
        setHotspots(response.hotspots);
        setCounts({
          modis: Number(bySensor.modis ?? 0),
          viirs_snpp: Number(bySensor.viirs_snpp ?? 0),
          viirs_noaa20: Number(bySensor.viirs_noaa20 ?? 0),
          viirs_noaa21: Number(bySensor.viirs_noaa21 ?? 0),
        });
        setTotalDetections(Number(response.metadata.filtered_hotspot_count ?? response.hotspots.length));
        const dataSource = String(response.metadata.data_source ?? "live");
        setSourceMode(usedDemo || dataSource === "demo" ? "demo" : dataSource.includes("cached") ? "cached" : "live");
        setUpdatedAt(new Date());
      } else {
        setSourceMode("unavailable");
        setError("NASA FIRMS is temporarily offline. Live backup observations remain ready in Fire Now.");
      }

      if (eventResult.status === "fulfilled") setEvents(eventResult.value.events);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const latestEvents = useMemo(
    () => [...events].sort((a, b) => +new Date(b.latest_detection) - +new Date(a.latest_detection)).slice(0, 4),
    [events]
  );
  const strongest = [...hotspots].sort((a, b) => (b.frp ?? 0) - (a.frp ?? 0))[0];

  const scrollToSatellite = (id: "terra" | "aqua" | "snpp" | "noaa20") => {
    setActiveSat(id);
    const el = document.getElementById(`sat-card-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  return (
    <main className="oc-home">
      <div className="oc-grid-lines" aria-hidden="true" />

      {/* ====================================================================
          HERO SECTION: 3D EARTH GLOBE, SATELLITE, HUD WIDGETS
          ==================================================================== */}
      <section className="oc-hero" aria-labelledby="oc-hero-heading">
        <div className="oc-hero-main">
          {/* Left Column: Hero Copy & Actions */}
          <div className="oc-hero-content">
            <div className="oc-kicker-badge">
              <span className="oc-kicker-dot" />
              <span className="oc-kicker-text">
                {sourceMode === "live"
                  ? "● LIVE NASA FIRMS NRT STREAM"
                  : sourceMode === "cached"
                  ? "● CACHED SATELLITE TELEMETRY"
                  : "● FOUR-WITNESS SATELLITE FLEET"}
              </span>
            </div>

            <h1 id="oc-hero-heading" className="oc-hero-title">
              Next Generation <br />
              <span className="glow-gradient">Satellite Systems</span>
            </h1>

            <p className="oc-hero-subtitle">
              Pioneering planetary active-fire surveillance from polar orbit. Continuous 375m fire radiative power
              detection and multi-witness harmonization built on NASA Terra, Aqua, Suomi-NPP, and NOAA-20 platforms.
            </p>

            <div className="oc-hero-actions">
              <Link to="/fire-map" className="oc-btn-primary">
                Explore Fire Now 3D
                <ArrowRight size={17} />
              </Link>

              <Link to="/fire-memory" className="oc-btn-secondary">
                <Clock size={16} />
                Build Fire Memory
              </Link>
            </div>

            {/* Quick Hero Telemetry Bar */}
            <div className="oc-hero-stats">
              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  4<span>SAT</span>
                </div>
                <div className="oc-stat-lbl">Active Witnesses</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  705<span>KM</span>
                </div>
                <div className="oc-stat-lbl">Polar Sun-Sync</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  375<span>M</span>
                </div>
                <div className="oc-stat-lbl">VIIRS Resolution</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  {totalDetections === null ? "—" : totalDetections.toLocaleString()}
                </div>
                <div className="oc-stat-lbl">Hotspots Returned</div>
              </div>
            </div>
          </div>

          {/* Right Column: 3D Earth Globe, Satellite & Floating Outcrowd HUD Cards */}
          <div className="oc-hero-visual">
            <OutcrowdEarthSatellite
              activeSatellite={activeSat}
              targetHotspot={strongest ? { lat: strongest.lat, lon: strongest.lon, frp: strongest.frp } : undefined}
            />

            {/* Floating HUD Widget 1: Top Right Telemetry */}
            <div className="oc-hud-card oc-hud-telemetry">
              <div className="oc-hud-header">
                <span className="oc-hud-title">ORBITAL TELEMETRY</span>
                <span className="oc-hud-tag">
                  <Radar size={10} />
                  SYNC
                </span>
              </div>
              <div className="oc-hud-body">
                <div className="oc-hud-row">
                  <span>PLATFORM</span>
                  <strong className="accent">NOAA-20 / VIIRS</strong>
                </div>
                <div className="oc-hud-row">
                  <span>ALTITUDE</span>
                  <strong>824.2 KM</strong>
                </div>
                <div className="oc-hud-row">
                  <span>INCLINATION</span>
                  <strong>98.7° SUN-SYNC</strong>
                </div>
                <div className="oc-hud-row">
                  <span>SWATH WIDTH</span>
                  <strong>3,040 KM</strong>
                </div>
              </div>
            </div>

            {/* Floating HUD Widget 2: Mid Left Target Coordinates */}
            <div className="oc-hud-card oc-hud-target">
              <div className="oc-hud-header">
                <span className="oc-hud-title">TARGET SECTOR</span>
                <span className="oc-hud-tag alert">
                  <Flame size={10} />
                  THERMAL
                </span>
              </div>
              <div className="oc-hud-body">
                <div className="oc-hud-row">
                  <span>COORDINATES</span>
                  <strong>
                    {strongest ? `${strongest.lat.toFixed(2)}°N, ${strongest.lon.toFixed(2)}°E` : "23.81°N, 90.41°E"}
                  </strong>
                </div>
                <div className="oc-hud-row">
                  <span>PEAK FIRE POWER</span>
                  <strong className="accent">{strongest?.frp ? `${strongest.frp.toFixed(1)} MW` : "142.8 MW"}</strong>
                </div>
                <div className="oc-hud-row">
                  <span>DETECTIONS</span>
                  <strong>{totalDetections ? `${totalDetections.toLocaleString()} Hotspots` : "Active Scan"}</strong>
                </div>
              </div>
            </div>

            {/* Floating HUD Widget 3: Bottom Right Fleet Status */}
            <div className="oc-hud-card oc-hud-fleet">
              <div className="oc-hud-header">
                <span className="oc-hud-title">FOUR-WITNESS PIPELINE</span>
                <span className="oc-hud-tag">
                  <Activity size={10} />
                  4/4
                </span>
              </div>
              <div className="oc-hud-body">
                <div className="oc-hud-row">
                  <span>MODIS FLEET</span>
                  <strong>TERRA + AQUA</strong>
                </div>
                <div className="oc-hud-row">
                  <span>VIIRS FLEET</span>
                  <strong>S-NPP + NOAA-20</strong>
                </div>
                <div className="oc-hud-row">
                  <span>CALIBRATION</span>
                  <strong className="accent">AQUA 13:30 EQV</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Alert banner if NASA FIRMS is offline */}
      {error && (
        <div
          style={{
            maxWidth: 1200,
            margin: "0 auto 20px",
            padding: "12px 24px",
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: 12,
            color: "#fca5a5",
            fontSize: 13,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <ShieldAlert size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* ====================================================================
          SECTION 1: THE FOUR WITNESSES (ANIMATED STACKING CARDS AS IN VIDEO)
          ==================================================================== */}
      {/* ====================================================================
          SECTION 1: THE FOUR WITNESSES (3D COVERFLOW SATELLITE CAROUSEL)
          ==================================================================== */}
      <section className="oc-section" id="fleet" aria-labelledby="fleet-heading" style={{ paddingTop: 40, overflow: "visible" }}>
        <div className="oc-section-header">
          <span className="oc-section-tag">CONSTELLATION FLEET</span>
          <h2 id="fleet-heading" className="oc-section-title">
            The Four-Witness Fire Intelligence
          </h2>
          <p className="oc-section-desc">
            Single-sensor fire monitoring suffers from orbital blind spots, cloud gaps, and diurnal timing bias.
            FlameSeek harmonizes four synchronized satellites into one continuous, evidence-backed observation layer.
          </p>
        </div>

        {/* 3D Coverflow Card Transition System with Pictures & Telemetry */}
        <Satellite3DCoverflow onSatelliteChange={(satId) => setActiveSat(satId)} />
      </section>

      {/* ====================================================================
          SECTION 2: DATA ECOSYSTEM MARQUEE (Eloqwnt 'Who we work with' ticker)
          ==================================================================== */}
      <section className="oc-section" style={{ padding: "30px 0" }} aria-label="Authoritative scientific data providers">
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <span className="oc-sat-kicker" style={{ justifyContent: "center" }}>• DATA ECOSYSTEM & CALIBRATION PARTNERS</span>
        </div>
        <div className="oc-marquee-wrap">
          <div className="oc-marquee-inner">
            {[...PARTNER_ORGANIZATIONS, ...PARTNER_ORGANIZATIONS].map((partner, index) => (
              <div key={`${partner.name}-${index}`} className="oc-partner-pill">
                <i>◈</i>
                <strong>{partner.name}</strong>
                <span>•</span>
                <span style={{ color: "var(--oc-text-muted)", fontSize: 12 }}>{partner.role}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ====================================================================
          SECTION 3: 7-STAGE PIPELINE (3D CARD TRANSITION SYSTEM)
          ==================================================================== */}
      <section className="oc-section" id="pipeline" aria-labelledby="pipeline-heading" style={{ overflow: "visible" }}>
        <div className="oc-section-header">
          <span className="oc-section-tag">SYSTEM ARCHITECTURE</span>
          <h2 id="pipeline-heading" className="oc-section-title">
            Past → Present → Identify → Verify → Forecast → Exposure
          </h2>
          <p className="oc-section-desc">
            A satellite hotspot is an observation, not automatically a confirmed wildfire. Every result is categorized
            through our rigorous 7-stage evidence pipeline. Explore each stage in the 3D transition system below.
          </p>
        </div>

        {/* 3D Cylindrical Card Transition System for the 7 Stages */}
        <Pipeline3DTransition />
      </section>

      {/* ====================================================================
          SECTION 4: LIVE TELEMETRY & OBSERVATION STREAM
          ==================================================================== */}
      <section className="oc-section" aria-labelledby="telemetry-heading">
        <div className="oc-section-header">
          <span className="oc-section-tag">REAL-TIME DATA STREAM</span>
          <h2 id="telemetry-heading" className="oc-section-title">
            Live Orbital Telemetry & Sensor Returns
          </h2>
          <p className="oc-section-desc">
            Direct feed from NASA FIRMS NRT and science archives, updated every 3 hours with sub-pixel Fire Radiative Power (MW).
          </p>
        </div>

        <div className="oc-dashboard-grid">
          {/* Left Panel: Live Sensor Distribution Chart */}
          <div className="oc-dashboard-panel">
            <div className="oc-panel-header">
              <span className="oc-panel-title">
                <Radio size={16} />
                Sensor Share (Last 24h Hotspots)
              </span>
              <span className="oc-hud-tag">LAST 24 H</span>
            </div>

            <div style={{ height: 260, width: "100%", position: "relative" }}>
              <Plot
                data={[
                  {
                    values: [counts.modis, counts.viirs_snpp, counts.viirs_noaa20, counts.viirs_noaa21],
                    labels: SENSOR_LABELS,
                    type: "pie",
                    hole: 0.62,
                    marker: {
                      colors: ["#38bdf8", "#00f2fe", "#f59e0b", "#ff4d26"],
                      line: { color: "#030712", width: 2 },
                    },
                    textinfo: "percent",
                    textfont: { color: "#f8fafc", family: "Space Grotesk, sans-serif", size: 11 },
                    hoverinfo: "label+value+percent",
                  },
                ]}
                layout={{
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  margin: { t: 10, r: 10, b: 10, l: 10 },
                  showlegend: false,
                  autosize: true,
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: "100%", height: "100%" }}
              />
              <div
                style={{
                  position: "absolute",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  textAlign: "center",
                  pointerEvents: "none",
                }}
              >
                <div style={{ fontFamily: "var(--oc-font-mono)", fontSize: 22, fontWeight: 800, color: "#ffffff" }}>
                  {totalDetections ? totalDetections.toLocaleString() : "—"}
                </div>
                <div style={{ fontSize: 10, color: "var(--oc-text-muted)", letterSpacing: "0.1em" }}>HOTSPOTS</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
              <div style={{ padding: "8px 12px", background: "rgba(11, 20, 40, 0.6)", borderRadius: 8, border: "1px solid rgba(56, 189, 248, 0.12)", fontSize: 12 }}>
                <span style={{ color: "#38bdf8" }}>● Terra & Aqua:</span> <strong>{counts.modis.toLocaleString()}</strong>
              </div>
              <div style={{ padding: "8px 12px", background: "rgba(11, 20, 40, 0.6)", borderRadius: 8, border: "1px solid rgba(56, 189, 248, 0.12)", fontSize: 12 }}>
                <span style={{ color: "#00f2fe" }}>● Suomi NPP:</span> <strong>{counts.viirs_snpp.toLocaleString()}</strong>
              </div>
              <div style={{ padding: "8px 12px", background: "rgba(11, 20, 40, 0.6)", borderRadius: 8, border: "1px solid rgba(56, 189, 248, 0.12)", fontSize: 12 }}>
                <span style={{ color: "#f59e0b" }}>● NOAA-20:</span> <strong>{counts.viirs_noaa20.toLocaleString()}</strong>
              </div>
              <div style={{ padding: "8px 12px", background: "rgba(11, 20, 40, 0.6)", borderRadius: 8, border: "1px solid rgba(56, 189, 248, 0.12)", fontSize: 12 }}>
                <span style={{ color: "#ff4d26" }}>● NOAA-21:</span> <strong>{counts.viirs_noaa21.toLocaleString()}</strong>
              </div>
            </div>
          </div>

          {/* Right Panel: Reconstructed Active Wildfire Events */}
          <div className="oc-dashboard-panel">
            <div className="oc-panel-header">
              <span className="oc-panel-title">
                <Flame size={16} />
                Recent Reconstructed Fire Events
              </span>
              <Link to="/fire-map" style={{ color: "var(--oc-cyan)", fontSize: 12, textDecoration: "none" }}>
                Open 3D Globe →
              </Link>
            </div>

            <div className="oc-event-list">
              {latestEvents.map((event) => (
                <Link to={`/fire-map?event=${event.event_id}`} key={event.event_id} className="oc-event-row">
                  <div className="oc-event-left">
                    <span className="oc-event-flare" />
                    <div>
                      <div className="oc-event-place">
                        {`Cluster near ${event.centroid.lat.toFixed(2)}°, ${event.centroid.lon.toFixed(2)}°`}
                      </div>
                      <div className="oc-event-sub">
                        <span>{event.observation_count} hotspots</span>
                        <span>•</span>
                        <span>{Math.round(event.max_frp ?? 0)} MW peak FRP</span>
                        <span>•</span>
                        <span>
                          {event.sensors
                            .map((s) => (s.toLowerCase().includes("modis") ? "MODIS" : "VIIRS"))
                            .filter((v, idx, arr) => arr.indexOf(v) === idx)
                            .join(" + ")}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="oc-event-right">
                    <span className="oc-event-age">{formatAge(event.latest_detection)}</span>
                    <ChevronRight size={14} color="#64748b" />
                  </div>
                </Link>
              ))}

              {!latestEvents.length && (
                <div style={{ textAlign: "center", padding: "40px 0", color: "var(--oc-text-muted)", fontSize: 13 }}>
                  Connecting to live satellite event reconstruction…
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ====================================================================
          SECTION 4B: HARMONIZED RECORD (offline multi-sensor snapshot)
          ==================================================================== */}
      <HarmonizedRecordSection />

      {/* ====================================================================
          SECTION 5: FAQ & METHODOLOGY (ANIMATED TIMELINE ROADMAP)
          ==================================================================== */}
      <section className="oc-section" aria-labelledby="faq-heading" style={{ overflow: "visible" }}>
        <div className="oc-section-header">
          <span className="oc-section-tag">FREQUENTLY ASKED QUESTIONS</span>
          <h2 id="faq-heading" className="oc-section-title">
            Scientific Methodology & Evidence Standards
          </h2>
          <p className="oc-section-desc">
            Learn why Four-Witness harmonization matters and how satellite active fire detection operates without proprietary black boxes.
          </p>
        </div>

        {/* Animated Perspective Roadmap Template Format */}
        <MethodologyRoadmap />
      </section>

      {/* ====================================================================
          SECTION 6: MISSION LAUNCH HORIZON CTA
          ==================================================================== */}
      <section className="oc-cta-horizon" aria-label="Explore FlameSeek live tools">
        <div className="oc-cta-content">
          <h2 className="oc-cta-title">
            Enter the FlameSeek <br />
            <span className="glow-gradient">Orbital Environment</span>
          </h2>

          <p className="oc-cta-desc">
            Explore live 3D planetary active-fire observations, build 25-year seasonal baselines, or analyze fire DNA fingerprints in any region across Earth.
          </p>

          <div className="oc-cta-btns">
            <Link to="/fire-map" className="oc-btn-primary">
              Launch Fire Now 3D Globe
              <ArrowRight size={17} />
            </Link>

            <Link to="/fire-memory" className="oc-btn-secondary">
              <Clock size={16} />
              Open Fire Memory
            </Link>

            <Link to="/fire-dna" className="oc-btn-secondary">
              <Activity size={16} />
              Analyze Fire DNA
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
