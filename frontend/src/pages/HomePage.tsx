import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import SensorShareChart from "../components/SensorShareChart";
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

const PARTNER_ORGANIZATIONS = [
  { name: "NASA FIRMS", role: "Fire detections" },
  { name: "NOAA NESDIS", role: "Satellite observations" },
  { name: "ESA Copernicus", role: "Imagery and fire reports" },
  { name: "Skyfield & CelesTrak", role: "Satellite pass estimates" },
  { name: "WorldPop", role: "Population estimates" },
  { name: "OpenStreetMap", role: "Roads and buildings" },
  { name: "GDELT Project", role: "News reports" },
  { name: "NIFC WFIGS", role: "US fire incident reports" },
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

    Promise.allSettled([loadHotspots()]).then(([hotspotResult]) => {
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
        setError("We could not load recent NASA observations. Open the fire map to retry.");
      }


      setLoading(false);
    });
    loadEvents().then((result) => { if (!cancelled) setEvents(result.events); }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const latestEvents = useMemo(
    () => [...events].sort((a, b) => +new Date(b.latest_detection) - +new Date(a.latest_detection)).slice(0, 4),
    [events]
  );
  const globeHotspots = useMemo(() => {
    const cells = new Set<string>();
    return [...hotspots].sort((a, b) => (b.frp ?? 0) - (a.frp ?? 0)).filter((point) => {
      const cell = `${Math.floor(point.lat / 8)},${Math.floor(point.lon / 8)}`;
      if (cells.has(cell)) return false;
      cells.add(cell);
      return true;
    }).slice(0, 24);
  }, [hotspots]);
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
                {loading ? "LOADING NASA OBSERVATIONS" : sourceMode === "demo" ? "SAMPLE DATA" : sourceMode === "live"
                  ? "RECENT NASA FIRE OBSERVATIONS"
                  : sourceMode === "cached"
                  ? "SAVED NASA OBSERVATIONS"
                  : "EXPLORE SATELLITE FIRE DATA"}
              </span>
            </div>

            <h1 id="oc-hero-heading" className="oc-hero-title">
              Understand fires <br />
              <span className="glow-gradient">with satellite data</span>
            </h1>

            <p className="oc-hero-subtitle">
              See where satellites have detected heat, explore past fire activity, and check the evidence behind each result. FlameSeek brings NASA fire observations together in one place.
            </p>

            <div className="oc-hero-actions">
              <Link to="/fire-map" className="oc-btn-primary">
                Open the fire map
                <ArrowRight size={17} />
              </Link>

              <Link to="/fire-calendar" className="oc-btn-secondary">
                <Clock size={16} />
                Explore fire history
              </Link>
            </div>

            {/* Quick Hero Telemetry Bar */}
            <div className="oc-hero-stats">
              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  4<span>SAT</span>
                </div>
                <div className="oc-stat-lbl">Featured satellites</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  2<span>TYPES</span>
                </div>
                <div className="oc-stat-lbl">Satellite sensors</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  375<span>M</span>
                </div>
                <div className="oc-stat-lbl">VIIRS pixel size</div>
              </div>

              <div className="oc-stat-item">
                <div className="oc-stat-val">
                  {totalDetections === null ? "—" : totalDetections.toLocaleString()}
                </div>
                <div className="oc-stat-lbl">Recent heat detections</div>
              </div>
            </div>
          </div>

          {/* Right Column: 3D Earth Globe, Satellite & Floating Outcrowd HUD Cards */}
          <div className="oc-hero-visual">
            <OutcrowdEarthSatellite
              activeSatellite={activeSat}
              targetHotspots={globeHotspots}
            />


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
          <span className="oc-section-tag">MEET THE SATELLITES</span>
          <h2 id="fleet-heading" className="oc-section-title">
            Different satellites, a clearer picture
          </h2>
          <p className="oc-section-desc">
            Satellites pass at different times and see different levels of detail. FlameSeek combines MODIS and VIIRS observations, including NOAA-21 where available. Clouds and gaps between passes can still hide fires.
          </p>
        </div>

        {/* 3D Coverflow Card Transition System with Pictures & Telemetry */}
        <Satellite3DCoverflow onSatelliteChange={(satId) => setActiveSat(satId)} />
      </section>

      {/* ====================================================================
          SECTION 2: DATA ECOSYSTEM MARQUEE (Eloqwnt 'Who we work with' ticker)
          ==================================================================== */}
      <section className="oc-section" style={{ padding: "30px 0" }} aria-label="Data sources used by FlameSeek">
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <span className="oc-sat-kicker" style={{ justifyContent: "center" }}>DATA SOURCES</span>
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
          <span className="oc-section-tag">EXPLORE THE TOOLS</span>
          <h2 id="pipeline-heading" className="oc-section-title">
            Follow a fire from first detection to further analysis
          </h2>
          <p className="oc-section-desc">
            Start with recent satellite detections, then explore history, related reports and possible impacts. Some analyses need more data before they can show a result.
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
          <span className="oc-section-tag">RECENT SATELLITE OBSERVATIONS</span>
          <h2 id="telemetry-heading" className="oc-section-title">
            What satellites have detected recently
          </h2>
          <p className="oc-section-desc">
            Recent heat detections from NASA FIRMS, grouped by satellite sensor. These are satellite observations, not a count of confirmed wildfires. Updates depend on data availability.
          </p>
        </div>

        <div className="oc-dashboard-grid">
          {/* Left Panel: Live Detections by sensor Chart */}
          <div className="oc-dashboard-panel">
            <div className="oc-panel-header">
              <span className="oc-panel-title">
                <Radio size={16} />
                Heat detections by satellite sensor
              </span>
              <span className="oc-hud-tag">PAST 24 HOURS</span>
            </div>

            <div style={{ height: 260, width: "100%", position: "relative" }}>
              <SensorShareChart counts={[counts.modis, counts.viirs_snpp, counts.viirs_noaa20, counts.viirs_noaa21]} labels={SENSOR_LABELS} />
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
                <div style={{ fontFamily: "var(--oc-font-mono)", fontSize: 22, fontWeight: 800, color: "var(--oc-text-primary)" }}>
                  {totalDetections ? totalDetections.toLocaleString() : "—"}
                </div>
                <div style={{ fontSize: 10, color: "var(--oc-text-muted)", letterSpacing: "0.1em" }}>HEAT DETECTIONS</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
              <div className="oc-sensor-summary">
                <span style={{ color: "var(--oc-sensor-terra, #38bdf8)" }}>● Terra & Aqua:</span> <strong>{counts.modis.toLocaleString()}</strong>
              </div>
              <div className="oc-sensor-summary">
                <span style={{ color: "var(--oc-sensor-snpp, #00f2fe)" }}>● Suomi NPP:</span> <strong>{counts.viirs_snpp.toLocaleString()}</strong>
              </div>
              <div className="oc-sensor-summary">
                <span style={{ color: "var(--oc-sensor-noaa20, #f59e0b)" }}>● NOAA-20:</span> <strong>{counts.viirs_noaa20.toLocaleString()}</strong>
              </div>
              <div className="oc-sensor-summary">
                <span style={{ color: "var(--oc-sensor-noaa21, #ff4d26)" }}>● NOAA-21:</span> <strong>{counts.viirs_noaa21.toLocaleString()}</strong>
              </div>
            </div>
          </div>

          {/* Right Panel: Reconstructed Active Wildfire Events */}
          <div className="oc-dashboard-panel">
            <div className="oc-panel-header">
              <span className="oc-panel-title">
                <Flame size={16} />
                Recent groups of fire detections
              </span>
              <Link to="/fire-map" style={{ color: "var(--oc-cyan)", fontSize: 12, textDecoration: "none" }}>
                Open fire map
              </Link>
            </div>

            <div className="oc-event-list">
              {latestEvents.map((event) => (
                <Link to={`/fire-map?event=${event.event_id}`} key={event.event_id} className="oc-event-row">
                  <div className="oc-event-left">
                    <span className="oc-event-flare" />
                    <div>
                      <div className="oc-event-place">
                        {`Detections near ${event.centroid.lat.toFixed(2)}°, ${event.centroid.lon.toFixed(2)}°`}
                      </div>
                      <div className="oc-event-sub">
                        <span>{event.observation_count} heat detections</span>
                        <span>•</span>
                        <span>{Math.round(event.max_frp ?? 0)} MW peak heat output</span>
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
                  No recent fire groups loaded. Open the map to check again.
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
          <span className="oc-section-tag">HOW WE CHECK THE DATA</span>
          <h2 id="faq-heading" className="oc-section-title">
            Understand what the results mean
          </h2>
          <p className="oc-section-desc">
            Learn how satellite observations become fire information, what we check, and where the limits are.
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
            Choose a place. <br />
            <span className="glow-gradient">Explore its fire activity.</span>
          </h2>

          <p className="oc-cta-desc">
            Open the map for recent detections, browse available fire history, or compare activity in a place you care about.
          </p>

          <div className="oc-cta-btns">
            <Link to="/fire-map" className="oc-btn-primary">
              Open the fire map
              <ArrowRight size={17} />
            </Link>

            <Link to="/fire-calendar" className="oc-btn-secondary">
              <Clock size={16} />
              Explore fire history
            </Link>

            <Link to="/fire-dna" className="oc-btn-secondary">
              <Activity size={16} />
              Compare fire patterns
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
