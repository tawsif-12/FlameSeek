import React, { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { RefreshCw, RotateCcw, Search, X } from "lucide-react";
import "./fireNow.css";
import { globePointKey, uniqueGlobePoints, uploadPointBatches, toggleObservationLayer } from "../utils/globePoints";
import { getHarmonizedHotspots, getCurrentHotspots, getEvent, getEvents, lookupEvent, normalizeApiError, runJob, searchPlaces, startEvidence } from "../api/client";
import { DEFAULT_SENSORS, aoiBBox, aoiContains, describeAoi, useAppContext } from "../context/AppContext";
import type { AOI, CaseMarker, FireEvent, FireEventSummary, ForecastHorizon, HotspotRecord, PlaceResult } from "../types/api";
import { BEHAVIOUR_COLORS, BEHAVIOUR_PLAIN, KIND_COLORS, KIND_LABELS, REALITY_WEIGHT } from "./fireCasePresentation";

const EventPanel = React.lazy(() => import("./EventPanel"));

type SatelliteLayer = "Terra" | "Aqua" | "S-NPP" | "NOAA-20" | "NOAA-21";
type LayerKey = SatelliteLayer | "Harmonized" | "Fire Events" | "FRP Columns" | "Forecast Corridor" | "Exposure" | "Boundaries";
type LightingMode = "Dawn" | "Day" | "Dusk" | "Night";
type ThemeMode = "Default" | "Faded" | "Mono" | "Ocean" | "Warm" | "Vivid";
type EarthMode = "Map" | "3D Terrain" | "Photorealistic";
type Period = "1" | "2" | "5" | "historical";
type ExposureMarker = { lat: number; lon: number; name: string; category: string };

// Fire Case marker fill: more solid as the confirmation level rises.
const REALITY_FILL: Record<string, number> = {
  "Confirmed fire": 0.8,
  "Highly likely fire": 0.6,
  "Possible fire (needs verification)": 0.35,
  "No external confirmation yet": 0.3,
  "Likely non-fire thermal anomaly": 0.25,
};
const AUTO_VERIFY_COUNT = 3;

const daylightBackgrounds: Record<LightingMode, string> = { Dawn: "#061f36", Day: "#031529", Dusk: "#071a30", Night: "#020817" };
const globeBaseColor = Cesium.Color.fromCssColorString("#0b2f63");
const defaultImageryStyle = { alpha: 1, brightness: 1, contrast: 1.02, gamma: 1, hue: 0, saturation: 1 };
const minimumTerrainZoomDistance = 20;
const minimumMapZoomDistance = 50000;

const locations = {
  "Atlantic View": { lat: 18.0, lon: -35.0, height: 14500000 },
  Bangladesh: { lat: 23.685, lon: 90.3563, height: 900000 },
  Amazon: { lat: -3.4653, lon: -62.2159, height: 1200000 },
  "California, USA": { lat: 38.5816, lon: -121.4944, height: 850000 },
  "Northern Australia": { lat: -12.4634, lon: 130.8456, height: 1000000 },
  Greece: { lat: 38.05, lon: 23.78, height: 750000 },
};

const nadirOrientation = { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 };
const obliqueOrientation = { heading: Cesium.Math.toRadians(18), pitch: Cesium.Math.toRadians(-52), roll: 0 };

const layerDefaults: Record<LayerKey, boolean> = { Terra: false, Aqua: false, "S-NPP": false, "NOAA-20": false, "NOAA-21": false, Harmonized: true, "Fire Events": false, "FRP Columns": false, "Forecast Corridor": true, Exposure: true, Boundaries: true };
const satelliteLayers: SatelliteLayer[] = ["Terra", "Aqua", "S-NPP", "NOAA-20", "NOAA-21"];
const satelliteColors: Record<SatelliteLayer, string> = { Terra: "#22c55e", Aqua: "#38bdf8", "S-NPP": "#facc15", "NOAA-20": "#fb923c", "NOAA-21": "#e879f9" };
// Esri's free reference overlay: country, state and district lines with place labels.
const BOUNDARIES_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer";
const periodLabels: Record<Period, string> = { "1": "Last 24 hours", "2": "Last 2 days", "5": "Last 5 days", historical: "Pick a past date" };
const LAYER_LABEL: Record<LayerKey, string> = { Terra: "MODIS · Terra", Aqua: "MODIS · Aqua", "S-NPP": "VIIRS · S-NPP", "NOAA-20": "VIIRS · NOAA-20", "NOAA-21": "VIIRS · NOAA-21", Harmonized: "Harmonized events", "Fire Events": "Fire cases", "FRP Columns": "Fire power bars", "Forecast Corridor": "Forecast area", Exposure: "Places nearby", Boundaries: "Administrative boundaries" };

function satelliteLayer(h: HotspotRecord): SatelliteLayer | null {
  if (h.sensor === "viirs_snpp") return "S-NPP";
  if (h.sensor === "viirs_noaa20") return "NOAA-20";
  if (h.sensor === "viirs_noaa21") return "NOAA-21";
  if (h.sensor !== "modis") return null;
  const satellite = h.satellite.trim().toLowerCase();
  return ["terra", "t"].includes(satellite) ? "Terra" : ["aqua", "a"].includes(satellite) ? "Aqua" : null;
}
const EXPOSURE_COLORS: Record<string, string> = {
  settlements: "#f8fafc",
  schools: "#60a5fa",
  hospitals: "#f472b6",
  power: "#facc15",
  critical_facilities: "#c084fc",
  agriculture: "#84cc16",
  forests: "#22c55e",
  protected_areas: "#14b8a6",
};

function sensorFamily(sensor: string) {
  return sensor === "modis" ? "MODIS" : sensor.startsWith("viirs") ? "VIIRS" : sensor.toUpperCase();
}

function hotspotKey(h: HotspotRecord) {
  return globePointKey(h);
}

function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number) {
  const toRad = Math.PI / 180;
  const h = Math.sin(((bLat - aLat) * toRad) / 2) ** 2 + Math.cos(aLat * toRad) * Math.cos(bLat * toRad) * Math.sin(((bLon - aLon) * toRad) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

/** Mark detections with an opposite-family detection within 15 km and 6 h (cross-sensor confirmation colour). */
function crossSensorSet(hotspots: HotspotRecord[]) {
  const confirmed = new Set<string>();
  const grid = new Map<string, HotspotRecord[]>();
  const cellOf = (h: HotspotRecord) => `${Math.floor(h.lat / 0.15)}|${Math.floor(h.lon / 0.15)}`;
  hotspots.forEach((h) => {
    const k = cellOf(h);
    grid.set(k, [...(grid.get(k) ?? []), h]);
  });
  hotspots.forEach((h) => {
    const [ci, cj] = cellOf(h).split("|").map(Number);
    const t = new Date(h.acq_datetime).getTime();
    for (let di = -1; di <= 1; di += 1) {
      for (let dj = -1; dj <= 1; dj += 1) {
        for (const o of grid.get(`${ci + di}|${cj + dj}`) ?? []) {
          if (sensorFamily(o.sensor) === sensorFamily(h.sensor)) continue;
          if (Math.abs(new Date(o.acq_datetime).getTime() - t) > 6 * 3600000) continue;
          if (distanceKm(h.lat, h.lon, o.lat, o.lon) <= 15) {
            confirmed.add(hotspotKey(h));
            return;
          }
        }
      }
    }
  });
  return confirmed;
}

function hotspotColor(h: HotspotRecord, confirmed: Set<string>, sensorColors: boolean) {
  if (sensorColors) {
    if (h.harmonized) return Cesium.Color.fromCssColorString("#f43f5e");
    const platform = satelliteLayer(h);
    return Cesium.Color.fromCssColorString(platform ? satelliteColors[platform] : "#94a3b8");
  }
  const frp = h.frp ?? 0;
  if (frp >= 100) return Cesium.Color.fromCssColorString("#b91c1c");
  if (frp >= 30) return Cesium.Color.fromCssColorString("#ea580c");
  if (frp >= 10) return Cesium.Color.fromCssColorString("#f59e0b");
  return Cesium.Color.fromCssColorString("#fde68a");
}

const HIGHLIGHT_COLOR = Cesium.Color.fromCssColorString("#facc15");
function isHighlightedHotspot(h: HotspotRecord) {
  return typeof h.place_hint === "string" && h.place_hint.length > 0;
}

function aoiIsBangladesh(aoi: AOI | null): boolean {
  if (!aoi) return false;
  const name = (aoi.name ?? "").toLowerCase();
  if (name.includes("bangladesh") || name.includes("dhaka") || name.includes("ashulia")) return true;
  const bbox = aoiBBox(aoi);
  if (!bbox) return false;
  const [w, s, e, n] = bbox;
  return w <= 90.38 && 90.38 <= e && s <= 23.85 && 23.85 <= n;
}

function themeClass(theme: ThemeMode) {
  return `theme-${theme.toLowerCase()}`;
}

function configureCameraController(viewer: Cesium.Viewer, mode: EarthMode) {
  const controller = viewer.scene.screenSpaceCameraController;
  controller.enableInputs = true;
  controller.enableZoom = true;
  controller.enableRotate = true;
  controller.enableTilt = mode !== "Map";
  controller.enableLook = true;
  controller.enableTranslate = true;
  controller.enableCollisionDetection = mode !== "Map";
  controller.minimumZoomDistance = mode === "Map" ? minimumMapZoomDistance : minimumTerrainZoomDistance;
  controller.maximumZoomDistance = 30000000;
  controller.inertiaSpin = 0.85;
  controller.inertiaTranslate = 0.9;
  controller.inertiaZoom = 0.8;
  controller.zoomEventTypes = [Cesium.CameraEventType.WHEEL, Cesium.CameraEventType.PINCH];
  controller.rotateEventTypes = [Cesium.CameraEventType.LEFT_DRAG];
  controller.tiltEventTypes = [
    Cesium.CameraEventType.RIGHT_DRAG,
    Cesium.CameraEventType.MIDDLE_DRAG,
    Cesium.CameraEventType.PINCH,
    { eventType: Cesium.CameraEventType.LEFT_DRAG, modifier: Cesium.KeyboardEventModifier.CTRL },
  ];
  controller.lookEventTypes = [
    { eventType: Cesium.CameraEventType.LEFT_DRAG, modifier: Cesium.KeyboardEventModifier.SHIFT },
    { eventType: Cesium.CameraEventType.RIGHT_DRAG, modifier: Cesium.KeyboardEventModifier.SHIFT },
  ];
  controller.translateEventTypes = [{ eventType: Cesium.CameraEventType.RIGHT_DRAG, modifier: Cesium.KeyboardEventModifier.CTRL }];
}

function isPositionVisibleFromCamera(position: Cesium.Cartesian3, cameraPosition: Cesium.Cartesian3) {
  const pointDirection = Cesium.Cartesian3.normalize(position, new Cesium.Cartesian3());
  const cameraDirection = Cesium.Cartesian3.normalize(cameraPosition, new Cesium.Cartesian3());
  return Cesium.Cartesian3.dot(pointDirection, cameraDirection) > -0.08;
}

/** Hide entities on the far side of the Earth so the globe reads as a solid planet. */
function updateHotspotOcclusion(viewer: Cesium.Viewer) {
  [...viewer.entities.values, ...viewer.dataSources.getByName("fire-observations").flatMap(source => source.entities.values)].forEach((entity) => {
    if (!entity.position) return;
    const position = entity.position.getValue(viewer.clock.currentTime);
    entity.show = position ? isPositionVisibleFromCamera(position, viewer.camera.positionWC) : false;
  });
  viewer.scene.requestRender();
}

function aoiOutline(aoi: AOI): number[][] {
  if (aoi.center && aoi.radius_km) {
    const [lon, lat] = aoi.center;
    return Array.from({ length: 73 }, (_, i) => {
      const a = (i / 72) * 2 * Math.PI;
      return [lon + (aoi.radius_km! / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.sin(a), lat + (aoi.radius_km! / 111.32) * Math.cos(a)];
    });
  }
  if (aoi.geometry) {
    return aoi.geometry.type === "Polygon" ? (aoi.geometry.coordinates as number[][][])[0] : [...(aoi.geometry.coordinates as number[][][][])].sort((a, b) => b[0].length - a[0].length)[0][0];
  }
  const b = aoiBBox(aoi)!;
  return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];
}

export default function CesiumFireGlobe() {
  const { aoi, setAoi, lockedArea } = useAppContext();
  const [searchParams] = useSearchParams();
  const route = useLocation();
  const navigate = useNavigate();
  const setSearchParams = (update: (current: URLSearchParams) => URLSearchParams, options: { replace: boolean }) => {
    navigate({ search: `?${update(searchParams)}`, hash: route.hash }, options);
  };
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const [mobilePanel, setMobilePanel] = useState<"filters" | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(layerDefaults);
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const [lighting] = useState<LightingMode>("Day");
  const [theme] = useState<ThemeMode>("Default");
  const [showImagery] = useState(true);
  const [earthMode] = useState<EarthMode>("3D Terrain");
  const [sensorColors, setSensorColors] = useState(true);
  const [showBuildings] = useState(true);
  const [tilesStatus, setTilesStatus] = useState<string | null>(null);
  const calendarDate = searchParams.get("date");
  const [period, setPeriod] = useState<Period>(calendarDate ? "historical" : "1");
  const [historicalDate, setHistoricalDate] = useState(() => calendarDate ?? new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10));
  const [hotspots, setHotspots] = useState<HotspotRecord[]>([]);
  const [rawHotspots, setRawHotspots] = useState<HotspotRecord[]>([]);
  const [events, setEvents] = useState<FireEventSummary[]>([]);
  const [autoVerify, setAutoVerify] = useState(true);
  const [verifying, setVerifying] = useState<Set<string>>(new Set());
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);
  // Events already auto-verified this session, and how many of this data load's budget are used.
  const attemptedRef = useRef<Set<string>>(new Set());
  const loadBudgetUsedRef = useRef(0);
  const verifyRunningRef = useRef(false);
  const autoVerifyRef = useRef(autoVerify);
  autoVerifyRef.current = autoVerify;
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const unmountedRef = useRef(false);
  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
    };
  }, []);
  const [eventMeta, setEventMeta] = useState<Record<string, unknown>>({});
  const [dataStatus, setDataStatus] = useState("Loading live FIRMS MODIS/VIIRS data...");
  const [feedState, setFeedState] = useState<"loading" | "live" | "partial" | "cached" | "ready" | "failed">("loading");
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [mergedCount, setMergedCount] = useState<number | null>(null);
  const [rawPreview, setRawPreview] = useState(false);
  const [backgroundRefresh, setBackgroundRefresh] = useState(false);
  const [processingPending, setProcessingPending] = useState(false);
  const loadSequence = useRef(0);
  const [eventStatus, setEventStatus] = useState<string | null>(null);
  const [filterToAoi, setFilterToAoi] = useState(Boolean(lockedArea) || searchParams.get("aoi") === "1");
  const [drawing, setDrawing] = useState(false);
  const [drawPoints, setDrawPoints] = useState<number[][]>([]);
  const [placeQuery, setPlaceQuery] = useState("");
  const [placeResults, setPlaceResults] = useState<PlaceResult[]>([]);
  const [placeSearchStatus, setPlaceSearchStatus] = useState<string | null>(null);
  const placeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => placeRequest.current?.abort(), []);
  const [radiusKm, setRadiusKm] = useState(50);
  const [selectedFire, setSelectedFire] = useState<{ event: FireEvent | null; detection: HotspotRecord | null } | null>(null);
  const selectedEvent = selectedFire?.event ?? null;
  const selectedDetection = selectedFire?.detection ?? null;
  const selectionSequence = useRef(0);
  const [selectionStatus, setSelectionStatus] = useState<string | null>(null);
  const [forecast, setForecast] = useState<{ horizon: ForecastHorizon | null; size: number }>({ horizon: null, size: 0 });
  const [exposure, setExposure] = useState<ExposureMarker[]>([]);
  const [viewerReady, setViewerReady] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [activeInsight, setActiveInsight] = useState<null | "snapshot" | "intensity" | "timeline" | "events">(null);
  const observationPointsRef = useRef<Cesium.PointPrimitiveCollection | null>(null);
  const buildingsRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const boundariesRef = useRef<Cesium.ImageryLayer | null>(null);
  const photorealisticTilesRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const photorealisticLoadingRef = useRef(false);
  const terrainRef = useRef<Cesium.TerrainProvider | null>(null);
  const ellipsoidTerrainRef = useRef<Cesium.EllipsoidTerrainProvider | null>(null);
  const lookupRef = useRef<Map<string, HotspotRecord>>(new Map());
  const drawingRef = useRef(false);
  const removeCameraOcclusionRef = useRef<Cesium.Event.RemoveCallback | null>(null);

  const visibleHotspots = useMemo(
    () => [
      ...(layers.Harmonized ? hotspots.filter((h) => rawPreview || Boolean(h.harmonized)) : []),
      ...rawHotspots.filter((h) => { const platform = satelliteLayer(h); return platform !== null && layers[platform]; }),
    ].filter((h) => !filterToAoi || !aoi || aoiContains(aoi, h.lat, h.lon)),
    [hotspots, rawHotspots, layers.Harmonized, layers.Terra, layers.Aqua, layers["S-NPP"], layers["NOAA-20"], layers["NOAA-21"], filterToAoi, aoi, rawPreview],
  );
  const visibleEvents = useMemo(
    () => events.filter((e) => e.observation_count >= 3 && (!filterToAoi || !aoi || aoiContains(aoi, e.centroid.lat, e.centroid.lon))),
    [events, filterToAoi, aoi],
  );
  const satelliteCounts = useMemo(() => {
    const counts = Object.fromEntries(satelliteLayers.map(layer => [layer, 0])) as Record<SatelliteLayer, number>;
    for (const h of rawHotspots) {
      const platform = satelliteLayer(h);
      if (platform && (!filterToAoi || !aoi || aoiContains(aoi, h.lat, h.lon))) counts[platform]++;
    }
    return counts;
  }, [rawHotspots, filterToAoi, aoi]);
  const confirmed = useMemo(() => crossSensorSet(hotspots), [hotspots]);
  const highlightRegion = useMemo(() => aoiIsBangladesh(aoi), [aoi]);
  // Find events whose centroid sits on top of one of our highlighted point clusters.
  const highlightedEventIds = useMemo(() => {
    if (!highlightRegion) return new Set<string>();
    const clusters = hotspots.filter(isHighlightedHotspot);
    if (clusters.length === 0) return new Set<string>();
    const ids = new Set<string>();
    for (const e of events) {
      for (const h of clusters) {
        if (distanceKm(e.centroid.lat, e.centroid.lon, h.lat, h.lon) <= 4) {
          ids.add(e.event_id);
          break;
        }
      }
    }
    return ids;
  }, [events, hotspots, highlightRegion]);
  // Map an event centroid to the nearest highlighted place name for pop-up labels.
  const placeForEvent = useMemo(() => {
    const clusters = hotspots.filter(isHighlightedHotspot);
    const lookup: Record<string, string> = {};
    for (const e of events) {
      let best: { d: number; name: string } | null = null;
      for (const h of clusters) {
        const d = distanceKm(e.centroid.lat, e.centroid.lon, h.lat, h.lon);
        if (d <= 6 && (!best || d < best.d)) best = { d, name: h.place_hint as string };
      }
      if (best) lookup[e.event_id] = best.name;
      else if (e.place_hint) lookup[e.event_id] = e.place_hint;
    }
    return lookup;
  }, [events, hotspots]);

  const stats = useMemo(() => {
    const modis = visibleHotspots.filter((h) => h.sensor === "modis").length;
    const viirs = visibleHotspots.length - modis;
    const crossConfirmed = visibleHotspots.filter((h) => confirmed.has(hotspotKey(h))).length;
    const frps = visibleHotspots.map((h) => h.frp ?? 0);
    const totalFrp = frps.reduce((s, v) => s + v, 0);
    const maxFrp = frps.length ? frps.reduce((max, value) => Math.max(max, value), 0) : 0;
    const intense = frps.filter((v) => v >= 100).length;
    const strong = frps.filter((v) => v >= 30 && v < 100).length;
    const mild = frps.filter((v) => v >= 10 && v < 30).length;
    const weak = frps.filter((v) => v < 10).length;
    const eventCount = visibleEvents.length;
    const eventArea = visibleEvents.reduce((s, e) => s + (e.extent_km2 ?? 0), 0);
    const topEvents = [...visibleEvents]
      .sort((a, b) => (b.observation_count ?? 0) - (a.observation_count ?? 0))
      .slice(0, 4);
    const behaviour = (eventMeta.behaviour_counts ?? {}) as Record<string, number>;
    const now = Date.now();
    const hours = Array.from({ length: 12 }, () => 0);
    for (const h of visibleHotspots) {
      const t = new Date(h.acq_datetime).getTime();
      if (!Number.isFinite(t)) continue;
      const dh = (now - t) / 3600000;
      if (dh < 0 || dh >= 24) continue;
      hours[Math.min(11, Math.floor(dh / 2))] += 1;
    }
    const hourMax = Math.max(1, ...hours);
    return { modis, viirs, crossConfirmed, totalFrp, maxFrp, intense, strong, mild, weak, eventCount, eventArea, topEvents, behaviour, hours, hourMax };
  }, [visibleHotspots, visibleEvents, confirmed, eventMeta]);

  useEffect(() => {
    drawingRef.current = drawing;
  }, [drawing]);

  async function loadData(quiet = false) {
    const sequence = ++loadSequence.current;
    if (!quiet) {
      setFeedState("loading");
      setMergedCount(null);
      selectionSequence.current += 1;
      setSelectedFire(null);
    }
    const historical = period === "historical";
    const days = historical ? 1 : Number(period);
    if (!historical) {
      if (!quiet) { setHotspots([]); setRawHotspots([]); }
      setDataStatus("Harmonizing FIRMS detections: quality checks, pixel footprints and event merging...");
    } else {
      setDataStatus(`Loading what satellites saw on ${historicalDate}...`);
    }
    try {
      const response = historical
        ? await getCurrentHotspots(DEFAULT_SENSORS, days, 4000, historicalDate, false)
        : await getHarmonizedHotspots(days);
      if (sequence !== loadSequence.current || unmountedRef.current) return;
      setRawPreview(Boolean(response.metadata.processing_pending || response.metadata.harmonization_unavailable));
      setProcessingPending(Boolean(response.metadata.processing_pending));
      setBackgroundRefresh(Boolean(response.metadata.refresh_in_progress));
      setFeedState(response.metadata.partial_coverage ? "partial" : response.metadata.data_source === "live" ? "live" : response.metadata.data_source === "cached_actual" ? "cached" : "ready");
      setLastRefresh(typeof response.metadata.snapshot_at === "string" ? response.metadata.snapshot_at : new Date().toISOString());
      setMergedCount(!historical && typeof response.metadata.events_total === "number" ? response.metadata.events_total : null);
      setHotspots(uniqueGlobePoints(response.hotspots));
      setRawHotspots(uniqueGlobePoints(historical ? response.hotspots : response.raw_hotspots ?? []));
      if (historical) setLayers((cur) => ({ ...cur, Harmonized: false, Terra: true, Aqua: true, "S-NPP": true, "NOAA-20": true, "NOAA-21": true }));
      const m = response.metadata as Record<string, number | string>;
      const missing = response.metadata.unavailable_live_sensors;
      const sourceLabel = response.metadata.partial_coverage
        ? `Partial FIRMS coverage (live sources unavailable: ${Array.isArray(missing) ? missing.join(", ") : "unknown"}; cached observations may be included)`
        : m.data_source === "live" ? "LIVE FIRMS" : m.data_source === "cached_actual" ? "cached FIRMS fallback" : String(m.data_source ?? "FIRMS");
      setDataStatus(
        response.metadata.processing_pending ? `${sourceLabel}: ${Number(m.raw_hotspot_count).toLocaleString()} real observations loaded. Matching events in the background.`
          : response.metadata.harmonization_unavailable ? `${sourceLabel}: showing real observations; event matching unavailable.`
          : historical ? `${sourceLabel} · On ${historicalDate}: ${Number(m.returned_hotspot_count).toLocaleString()} satellite detections.`
          : `${sourceLabel} · ${periodLabels[period]}: ${Number(m.raw_hotspot_count).toLocaleString()} detections → ${Number(m.events_total ?? 0).toLocaleString()} footprint-merged events; showing ${Number(m.returned_hotspot_count).toLocaleString()}. Procedure Steps 1–4. Calibrated activity and Monte Carlo uncertainty await data.`,
      );
      if (!historical) {
        setEvents([]);
        setEventStatus("One point per footprint-merged event. Click a point for its observation count, satellites and footprint uncertainty. FRP is the maximum per-overpass sum, never a sum across time.");
        return;
      }
    } catch (error) {
      if (sequence !== loadSequence.current || unmountedRef.current) return;
      setBackgroundRefresh(false);
      setProcessingPending(false);
      if (quiet) { setDataStatus(`Refresh unavailable: ${normalizeApiError(error)}. Keeping loaded observations.`); return; }
      setFeedState("failed");
      setHotspots([]);
      setRawHotspots([]);
      setEvents([]);
      setDataStatus(`FIRMS request failed: ${normalizeApiError(error)}. No fire points loaded.`);
      setEventStatus("Fire grouping paused because observations could not be loaded. Refresh to retry.");
      return;
    }
    if (historical) {
      setEvents([]);
      setEventStatus("Fires are grouped only for recent days. Use Burning Calendar to look at past years in one area.");
      return;
    }
    setEventStatus("Grouping heat spots into separate fires...");
    try {
      const response = await getEvents(Math.max(2, days), 4000, false);
      loadBudgetUsedRef.current = 0;
      setEvents(response.events);
      setEventMeta(response.metadata);
      const sourceLabel = response.metadata.data_source === "live" ? "LIVE FIRMS" : response.metadata.data_source === "cached_actual" ? "cached FIRMS fallback" : "FIRMS";
      setEventStatus(`${sourceLabel} · ${Number(response.metadata.multi_detection_events).toLocaleString()} fires were seen more than once (from ${Number(response.metadata.detections).toLocaleString()} heat spots).`);
    } catch (error) {
      setEvents([]);
      setEventStatus(`Event reconstruction unavailable: ${normalizeApiError(error)}`);
    }
  }

  useEffect(() => {
    if (!backgroundRefresh || period === "historical") return;
    const timer = window.setTimeout(() => { void loadData(true); }, 10000);
    return () => window.clearTimeout(timer);
  }, [backgroundRefresh, hotspots, period, historicalDate]);

  async function waitForContainerSize(element: HTMLDivElement) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const { width, height } = element.getBoundingClientRect();
      if (width > 0 && height > 0) return true;
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
    return false;
  }

  async function loadPhotorealisticTiles(viewer: Cesium.Viewer) {
    if (photorealisticTilesRef.current || photorealisticLoadingRef.current) return;
    photorealisticLoadingRef.current = true;
    setTilesStatus("Loading photorealistic 3D tiles...");
    try {
      const googleMapsKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
      const tileset = await Cesium.createGooglePhotorealistic3DTileset(
        { key: googleMapsKey || undefined, onlyUsingWithGoogleGeocoder: true },
        { show: earthMode === "Photorealistic", maximumScreenSpaceError: 4, dynamicScreenSpaceError: false, skipLevelOfDetail: false, enableCollision: true, immediatelyLoadDesiredLevelOfDetail: true },
      );
      if (viewer.isDestroyed()) return;
      tileset.show = earthMode === "Photorealistic";
      viewer.scene.primitives.add(tileset);
      photorealisticTilesRef.current = tileset;
      viewer.scene.globe.show = earthMode !== "Photorealistic";
      setTilesStatus(null);
      viewer.scene.requestRender();
    } catch (error) {
      setTilesStatus(error instanceof Error ? error.message : "Photorealistic 3D tiles are unavailable for this key.");
    } finally {
      photorealisticLoadingRef.current = false;
    }
  }

  async function openEvent(eventId: string, detection: HotspotRecord | null, sequence = ++selectionSequence.current) {
    setSelectedFire({ event: null, detection });
    setSelectionStatus("Loading fire event...");
    try {
      const ev = await getEvent(eventId);
      if (sequence !== selectionSequence.current) return;
      setSelectedFire({ event: ev, detection });
      setSelectionStatus(null);
    } catch (error) {
      if (sequence === selectionSequence.current) setSelectionStatus(normalizeApiError(error));
    }
  }

  async function openDetection(h: HotspotRecord) {
    const sequence = ++selectionSequence.current;
    setSelectedFire({ event: null, detection: h });
    setForecast({ horizon: null, size: 0 });
    setExposure([]);
    setSelectionStatus("Finding the fire event this detection belongs to...");
    try {
      const lookup = h.lookup_detection ?? h;
      const eventId = await lookupEvent(lookup.sensor, lookup.lat, lookup.lon, lookup.acq_datetime);
      if (sequence !== selectionSequence.current) return;
      await openEvent(eventId, h, sequence);
    } catch (error) {
      if (sequence === selectionSequence.current) setSelectionStatus(`${normalizeApiError(error)} Event analysis is unavailable; satellite details are in Sighting.`);
    }
  }

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;
    let disposed = false;

    async function initializeViewer() {
      try {
        if (!containerRef.current || disposed) return;
        const containerReady = await waitForContainerSize(containerRef.current);
        if (!containerReady || !containerRef.current || disposed) {
          setViewerError("3D map container is not ready yet.");
          return;
        }
        const cesiumIonToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
        if (cesiumIonToken) Cesium.Ion.defaultAccessToken = cesiumIonToken;
        const ellipsoidTerrain = new Cesium.EllipsoidTerrainProvider();
        ellipsoidTerrainRef.current = ellipsoidTerrain;
        const localImageryProvider = () =>
          Cesium.SingleTileImageryProvider.fromUrl("/textures/earth_day_2048.jpg", { credit: "NASA Earth imagery (illustrative basemap)" });
        let worldImageryProvider: Cesium.ImageryProvider;
        if (cesiumIonToken) {
          try {
            worldImageryProvider = await Cesium.createWorldImageryAsync({ style: Cesium.IonWorldImageryStyle.AERIAL });
          } catch {
            // An expired, malformed, or restricted ion token must not prevent the
            // viewer itself from loading. Natural Earth ships with Cesium locally.
            worldImageryProvider = await localImageryProvider();
          }
        } else {
          worldImageryProvider = await localImageryProvider();
        }

        const viewer = new Cesium.Viewer(containerRef.current, {
          contextOptions: { webgl: { alpha: true, premultipliedAlpha: false, antialias: true } },
          // Cesium's OIT composite can leave an opaque black limb on an alpha canvas.
          orderIndependentTranslucency: false,
          animation: false,
          baseLayer: new Cesium.ImageryLayer(worldImageryProvider),
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          sceneModePicker: false,
          selectionIndicator: true,
          timeline: false,
          infoBox: false,
          navigationInstructionsInitiallyVisible: false,
          terrainProvider: ellipsoidTerrain,
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
        });
        // GPU point primitives avoid one tracked Entity and terrain subscription per observation.
        observationPointsRef.current = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
        viewer.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

        viewer.selectedEntityChanged.addEventListener((entity) => {
          if (drawingRef.current || !entity) return;
          const id = String(entity.id);
          if (id.startsWith("hs:") || id.startsWith("hz:")) {
            const h = lookupRef.current.get(id.split("#")[0]);
            if (h) void openDetection(h);
          } else if (id.startsWith("ev:")) {
            void openEvent(id.slice(3).split("#")[0], null);
          }
        });

        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
          if (!drawingRef.current) {
            const picked = viewer.scene.pick(click.position);
            const observation = picked?.id?.fireObservation as HotspotRecord | undefined;
            if (observation) { void openDetection(observation); return; }
            const members = picked?.id?.fireCluster as Cesium.Entity[] | undefined;
            if (members?.length) void viewer.flyTo(members, { duration: 1 });
            return;
          }
          const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
          if (!cartesian) return;
          const c = Cesium.Cartographic.fromCartesian(cartesian);
          setDrawPoints((pts) => [...pts, [Cesium.Math.toDegrees(c.longitude), Cesium.Math.toDegrees(c.latitude)]]);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        viewer.scene.renderError.addEventListener((_scene, error) => {
          const message = error instanceof Error ? error.message : String(error);
          if (message.includes("Expected width to be greater than 0")) {
            viewer.resize();
            viewer.scene.requestRender();
            return;
          }
          setViewerError(message);
        });

        viewer.scene.globe.baseColor = globeBaseColor;
        viewer.scene.globe.maximumScreenSpaceError = 1.5;
        viewer.scene.globe.depthTestAgainstTerrain = true;
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.globe.atmosphereLightIntensity = 5;
        viewer.scene.globe.atmosphereSaturationShift = -0.45;
        viewer.scene.globe.atmosphereBrightnessShift = -0.08;
        configureCameraController(viewer, earthMode);
        viewer.scene.backgroundColor = Cesium.Color.TRANSPARENT;
        if (viewer.scene.skyBox) viewer.scene.skyBox.show = false;
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.saturationShift = -0.55;
          viewer.scene.skyAtmosphere.brightnessShift = -0.15;
        }
        // A camera-relative sun keeps the interactive daytime hemisphere readable.
        const daylightSun = new Cesium.DirectionalLight({ direction: new Cesium.Cartesian3(1, 0, 0), intensity: 1.6 });
        viewer.scene.light = daylightSun;
        viewer.scene.preRender.addEventListener(() => {
          const direction = Cesium.Cartesian3.add(viewer.camera.directionWC,
            Cesium.Cartesian3.multiplyByScalar(viewer.camera.rightWC, 0.45, new Cesium.Cartesian3()), new Cesium.Cartesian3());
          Cesium.Cartesian3.add(direction, Cesium.Cartesian3.multiplyByScalar(viewer.camera.upWC, -0.35, new Cesium.Cartesian3()), direction);
          Cesium.Cartesian3.normalize(direction, daylightSun.direction);
        });
        void Cesium.SingleTileImageryProvider.fromUrl("/textures/earth_clouds_1024.png", { credit: "Cloud texture: illustrative, not current weather" }).then(provider => {
          if (disposed || viewer.isDestroyed()) return;
          const clouds = viewer.imageryLayers.addImageryProvider(provider);
          clouds.alpha = 0.22;
          clouds.colorToAlpha = Cesium.Color.BLACK;
          clouds.colorToAlphaThreshold = 0.12;
          viewer.scene.preRender.addEventListener(() => {
            clouds.show = viewer.camera.positionCartographic.height > 7000000 && viewer.imageryLayers.get(0).show;
          });
          viewer.scene.requestRender();
        }).catch(() => undefined);
        viewer.scene.sun = undefined;
        viewer.scene.moon = undefined;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(locations["Atlantic View"].lon, locations["Atlantic View"].lat, locations["Atlantic View"].height),
          orientation: nadirOrientation,
        });
        removeCameraOcclusionRef.current = viewer.camera.changed.addEventListener(() => updateHotspotOcclusion(viewer));
        viewerRef.current = viewer;
        setViewerError(null);
        setViewerReady(true);

        void Cesium.ArcGisMapServerImageryProvider.fromUrl(BOUNDARIES_URL)
          .then((provider) => {
            if (disposed || viewer.isDestroyed()) return;
            const boundaries = viewer.imageryLayers.addImageryProvider(provider);
            boundaries.show = layersRef.current.Boundaries;
            boundariesRef.current = boundaries;
            viewer.scene.requestRender();
          })
          .catch(() => undefined);

        if (cesiumIonToken) {
          void Cesium.createWorldTerrainAsync()
            .then((terrainProvider) => {
              if (disposed || viewer.isDestroyed()) return;
              terrainRef.current = terrainProvider;
              if (earthMode !== "Map") viewer.terrainProvider = terrainProvider;
              viewer.scene.requestRender();
            })
            .catch(() => undefined);
          void Cesium.createOsmBuildingsAsync()
            .then((buildings) => {
              if (disposed || viewer.isDestroyed()) return;
              buildings.show = earthMode === "3D Terrain" && showBuildings;
              viewer.scene.primitives.add(buildings);
              buildingsRef.current = buildings;
              viewer.scene.requestRender();
            })
            .catch(() => undefined);
        }
      } catch (error) {
        setViewerError(error instanceof Error ? error.message : "Cesium failed to initialize.");
      }
    }

    void initializeViewer();
    return () => {
      disposed = true;
      setViewerReady(false);
      removeCameraOcclusionRef.current?.();
      removeCameraOcclusionRef.current = null;
      viewerRef.current?.destroy();
      viewerRef.current = null;
      observationPointsRef.current = null;
      buildingsRef.current = null;
      boundariesRef.current = null;
      photorealisticTilesRef.current = null;
      photorealisticLoadingRef.current = false;
      terrainRef.current = null;
      ellipsoidTerrainRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, historicalDate]);

  useEffect(() => {
    if (!lockedArea || !aoi || !viewerReady) return;
    const box = aoiBBox(aoi);
    if (box) viewerRef.current?.camera.setView({ destination: Cesium.Rectangle.fromDegrees(...box) });
  }, [lockedArea, aoi, viewerReady]);

  // Deep link: /fire-map?event=EV-XXXX opens that event once events are loaded.
  useEffect(() => {
    const linked = searchParams.get("event");
    if (!linked || !viewerReady || events.length === 0 || selectedEvent?.event_id === linked) return;
    const summary = events.find((e) => e.event_id === linked);
    if (summary) {
      const pad = 0.4;
      flyToBBox([summary.bbox[0] - pad, summary.bbox[1] - pad, summary.bbox[2] + pad, summary.bbox[3] + pad]);
    }
    void openEvent(linked, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, viewerReady]);

  const hadEventRef = useRef(false);
  useEffect(() => {
    if (selectedEvent) {
      hadEventRef.current = true;
      setSearchParams(current => { const next = new URLSearchParams(current); next.set('event', selectedEvent.event_id); return next; }, { replace: true });
    } else if (hadEventRef.current) {
      // Only clear the link when the user closes an open event, not before a linked one loads.
      hadEventRef.current = false;
      setSearchParams(current => { const next = new URLSearchParams(current); next.delete('event'); return next; }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEvent]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const syncTheme = () => {
      const isDayTheme = document.documentElement.dataset.theme === "day";
      // Let the theme-aware CSS background and grid show through the canvas.
      viewer.scene.backgroundColor = Cesium.Color.TRANSPARENT;
      viewer.scene.globe.enableLighting = isDayTheme;
      viewer.scene.globe.baseColor = globeBaseColor;
      viewer.scene.globe.showGroundAtmosphere = !isDayTheme;
      // Avoid dark atmospheric/FXAA fringes against the transparent day canvas.
      viewer.scene.postProcessStages.fxaa.enabled = !isDayTheme;
      viewer.scene.globe.dynamicAtmosphereLighting = false;
      viewer.scene.globe.atmosphereSaturationShift = isDayTheme ? -0.15 : -0.45;
      viewer.scene.globe.atmosphereBrightnessShift = isDayTheme ? 0.05 : -0.08;
      viewer.scene.globe.lambertDiffuseMultiplier = isDayTheme ? 1.65 : 1;
      if (viewer.scene.skyAtmosphere) {
        // The sky shell creates a dark fringe when composited over white.
        // Ground atmosphere retains the daylight haze without that outer rim.
        viewer.scene.skyAtmosphere.show = !isDayTheme;
        viewer.scene.skyAtmosphere.saturationShift = isDayTheme ? -0.2 : -0.55;
        viewer.scene.skyAtmosphere.brightnessShift = isDayTheme ? 0.08 : -0.15;
      }
      if (viewer.scene.skyBox) viewer.scene.skyBox.show = false;
      viewer.scene.requestRender();
    };
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [lighting, viewerReady]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const baseLayer = viewer.imageryLayers.get(0);
    if (baseLayer) {
      baseLayer.show = (earthMode !== "Photorealistic" || !photorealisticTilesRef.current) && showImagery;
      baseLayer.alpha = theme === "Faded" ? 0.82 : defaultImageryStyle.alpha;
      baseLayer.saturation = theme === "Mono" ? 0 : theme === "Vivid" ? 1.22 : theme === "Ocean" ? 1.12 : defaultImageryStyle.saturation;
      baseLayer.brightness = theme === "Faded" ? 1.04 : theme === "Warm" ? 1.02 : defaultImageryStyle.brightness;
      baseLayer.contrast = theme === "Faded" ? 0.92 : theme === "Mono" ? 1.06 : theme === "Vivid" ? 1.14 : defaultImageryStyle.contrast;
      baseLayer.gamma = theme === "Warm" ? 0.98 : defaultImageryStyle.gamma;
      baseLayer.hue = theme === "Ocean" ? -0.02 : theme === "Warm" ? 0.025 : defaultImageryStyle.hue;
    }
    if (buildingsRef.current) buildingsRef.current.show = earthMode === "3D Terrain" && showBuildings;
    if (photorealisticTilesRef.current) photorealisticTilesRef.current.show = earthMode === "Photorealistic";
    viewer.scene.requestRender();
  }, [earthMode, lighting, showBuildings, showImagery, theme, viewerReady]);



  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !boundariesRef.current) return;
    boundariesRef.current.show = layers.Boundaries;
    viewer.scene.requestRender();
  }, [layers.Boundaries, viewerReady]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    if (earthMode === "Photorealistic") void loadPhotorealisticTiles(viewer);
    const terrainProvider = earthMode === "Map" ? ellipsoidTerrainRef.current : terrainRef.current;
    if (terrainProvider) viewer.terrainProvider = terrainProvider;
    configureCameraController(viewer, earthMode);
    viewer.scene.globe.show = earthMode !== "Photorealistic" || !photorealisticTilesRef.current;
    viewer.scene.requestRender();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [earthMode, viewerReady]);

  // Upload large satellite layers in bounded batches so controls remain responsive.
  // Selection, forecasts and evidence updates do not rebuild observation points.
  useEffect(() => {
    const viewer = viewerRef.current;
    const points = observationPointsRef.current;
    if (!viewer || !points || !viewerReady) return;
    points.removeAll();
    const colors = new Map<string, Cesium.Color>();
    return uploadPointBatches(visibleHotspots, h => {
      const platform = satelliteLayer(h);
      const css = h.harmonized ? "#ef4444" : platform ? satelliteColors[platform] : "#ef4444";
      if (!colors.has(css)) colors.set(css, Cesium.Color.fromCssColorString(css));
      points.add({
        position: Cesium.Cartesian3.fromDegrees(h.lon, h.lat, 30),
        pixelSize: 5,
        color: colors.get(css)!,
        id: { fireObservation: h },
      });
    }, () => { if (!viewer.isDestroyed()) viewer.scene.requestRender(); });
  }, [visibleHotspots, viewerReady]);

  // Only the small selected-event and analysis overlays use tracked entities.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.entities.removeAll();
    lookupRef.current = new Map();

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (layers["Fire Events"]) {
      visibleEvents.forEach((e) => {
        // Fire Case marker: hollow while unchecked, fill colour = fire type, outline weight = confirmation level, faded once ended.
        const c = e.case;
        const baseColor = Cesium.Color.fromCssColorString(KIND_COLORS[c?.kind ?? "unknown"]);
        const ended = c?.state === "Ended";
        const fillAlpha = !c?.evidence_checked ? 0 : ended ? 0.12 : REALITY_FILL[c.reality] ?? 0.3;
        // Pulse while the case is still collecting evidence.
        const pulsing = verifying.has(e.event_id) || Boolean(c?.evidence_checked && c.provisional && !ended);
        const selected = selectedEvent?.event_id === e.event_id;
        const isHighlighted = highlightedEventIds.has(e.event_id);
        const placeLabel = placeForEvent[e.event_id];
        const color = isHighlighted ? HIGHLIGHT_COLOR : baseColor.withAlpha(ended ? 0.45 : 1);
        const caseText = c?.evidence_checked ? `${c.reality} · ${KIND_LABELS[c.kind]} · ${c.state}${c.provisional ? " (provisional)" : ""}` : `Case open · ${c?.state ?? e.behaviour_state}`;
        viewer.entities.add({
          id: `ev:${e.event_id}`,
          name: placeLabel ? `${placeLabel} · ${caseText}` : caseText,
          position: Cesium.Cartesian3.fromDegrees(e.centroid.lon, e.centroid.lat, 0),
          point: {
            pixelSize: Math.min(24, 8 + Math.log2(e.observation_count) * 2) + (isHighlighted ? 4 : 0),
            color: color.withAlpha(isHighlighted ? 0.45 : fillAlpha),
            outlineColor: color,
            outlineWidth: pulsing
              ? new Cesium.CallbackProperty(() => (REALITY_WEIGHT[c?.reality ?? ""] ?? 2) + (selected ? 2 : 0) + 2.5 * (1 + Math.sin(Date.now() / 220)), false)
              : (isHighlighted ? 5 : REALITY_WEIGHT[c?.reality ?? ""] ?? 2) + (selected ? 2 : 0),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: 0,
          },
          label: isHighlighted && placeLabel
            ? {
                text: placeLabel,
                font: "bold 12px Inter, sans-serif",
                fillColor: HIGHLIGHT_COLOR,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                pixelOffset: new Cesium.Cartesian2(0, -22),
                showBackground: true,
                backgroundColor: Cesium.Color.fromCssColorString("#0b1220").withAlpha(0.75),
                backgroundPadding: new Cesium.Cartesian2(6, 3),
                heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              }
            : undefined,
        });
        if (e.hull.length >= 3) {
          viewer.entities.add({
            id: `ev:${e.event_id}#hull`,
            position: Cesium.Cartesian3.fromDegrees(e.centroid.lon, e.centroid.lat, 0),
            polyline: { positions: Cesium.Cartesian3.fromDegreesArray([...e.hull, e.hull[0]].flat()), width: isHighlighted ? 4 : selected ? 3 : 1.5, material: color, clampToGround: true },
          });
        }
      });
    }

    // Keep the exact clicked observation marked, including while event lookup runs.
    const selectedPosition = selectedDetection
      ? { lon: selectedDetection.lon, lat: selectedDetection.lat }
      : selectedEvent?.centroid;
    if (selectedPosition) {
      const markerId = selectedDetection ? `${hotspotKey(selectedDetection)}#selected` : `ev:${selectedEvent!.event_id}#selected`;
      if (selectedDetection) lookupRef.current.set(hotspotKey(selectedDetection), selectedDetection);
      const ring = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="18" fill="#082f4933" stroke="#082f49" stroke-width="6"/><circle cx="24" cy="24" r="18" fill="none" stroke="#ffffff" stroke-width="3"/><path d="M24 1v10M24 37v10M1 24h10M37 24h10" stroke="#082f49" stroke-width="5"/><path d="M24 1v10M24 37v10M1 24h10M37 24h10" stroke="#22d3ee" stroke-width="2"/></svg>`;
      viewer.entities.add({
        id: markerId,
        name: "Selected fire location",
        position: Cesium.Cartesian3.fromDegrees(selectedPosition.lon, selectedPosition.lat),
        billboard: {
          image: `data:image/svg+xml,${encodeURIComponent(ring)}`,
          width: 48, height: 48,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: "Selected",
          font: "bold 12px sans-serif",
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString("#082f49"),
          backgroundPadding: new Cesium.Cartesian2(8, 5),
          pixelOffset: new Cesium.Cartesian2(0, -36),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }

    // Selected event: every linked detection with its approximate pixel footprint (scan x track).
    if (selectedEvent) {
      selectedEvent.detections.forEach((d, i) => {
        const scan = d.scan_km && d.scan_km <= 6 ? d.scan_km : d.sensor === "modis" ? 1 : 0.375;
        const track = d.track_km && d.track_km <= 6 ? d.track_km : d.sensor === "modis" ? 1 : 0.375;
        const halfLat = track / 2 / 111.32;
        const halfLon = scan / 2 / (111.32 * Math.max(Math.cos((d.lat * Math.PI) / 180), 0.01));
        const color = d.sensor === "modis" ? Cesium.Color.LIME : Cesium.Color.YELLOW;
        const id = `hs:${d.sensor}|${d.lat}|${d.lon}|${d.acq_datetime}`;
        lookupRef.current.set(id, d);
        viewer.entities.add({
          id: `${id}#fp${i}`,
          position: Cesium.Cartesian3.fromDegrees(d.lon, d.lat, 0),
          rectangle: { coordinates: Cesium.Rectangle.fromDegrees(d.lon - halfLon, d.lat - halfLat, d.lon + halfLon, d.lat + halfLat), material: color.withAlpha(0.35) },
        });
      });
    }

    // Keep user-drawn shapes visible, without highlighting selected countries/places.
    if (aoi && (aoi.kind === "polygon" || aoi.kind === "radius" || aoi.kind === "bbox")) {
      const outline = aoiOutline(aoi);
      const b = aoiBBox(aoi)!;
      viewer.entities.add({
        id: "aoi:outline",
        position: Cesium.Cartesian3.fromDegrees((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, 0),
        polyline: { positions: Cesium.Cartesian3.fromDegreesArray(outline.flat()), width: 2.5, material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.fromCssColorString("#f97316") }), clampToGround: true },
      });
    }
    if (drawPoints.length > 0) {
      viewer.entities.add({
        id: "aoi:draft",
        position: Cesium.Cartesian3.fromDegrees(drawPoints[0][0], drawPoints[0][1], 0),
        polyline: drawPoints.length > 1 ? { positions: Cesium.Cartesian3.fromDegreesArray(drawPoints.flat()), width: 2, material: Cesium.Color.ORANGE, clampToGround: true } : undefined,
        point: { pixelSize: 8, color: Cesium.Color.ORANGE },
      });
    }

    if (layers["Forecast Corridor"] && forecast.horizon) {
      const half = forecast.size / 2;
      forecast.horizon.cells.forEach((c, i) => {
        const color = c.p >= 0.6 ? "#b91c1c" : c.p >= 0.3 ? "#f97316" : "#fde047";
        viewer.entities.add({
          id: `fc:${i}`,
          position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, 0),
          rectangle: { coordinates: Cesium.Rectangle.fromDegrees(c.lon - half, c.lat - half, c.lon + half, c.lat + half), material: Cesium.Color.fromCssColorString(color).withAlpha(0.2 + 0.5 * c.p) },
        });
      });
    }

    if (layers.Exposure) {
      exposure.forEach((x, i) => {
        viewer.entities.add({
          id: `ex:${i}`,
          name: x.name,
          position: Cesium.Cartesian3.fromDegrees(x.lon, x.lat, 0),
          point: { pixelSize: 6, color: Cesium.Color.fromCssColorString(EXPOSURE_COLORS[x.category] ?? "#e2e8f0"), outlineColor: Cesium.Color.BLACK, outlineWidth: 1, heightReference: Cesium.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: 0 },
          label: x.category === "settlements" || x.category === "hospitals" || x.category === "schools"
            ? { text: x.name, font: "11px Inter, sans-serif", fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 2, style: Cesium.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new Cesium.Cartesian2(0, -12), distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 250000), heightReference: Cesium.HeightReference.CLAMP_TO_GROUND }
            : undefined,
        });
      });
    }

    updateHotspotOcclusion(viewer);
    viewer.scene.requestRender();
  }, [aoi, drawPoints, exposure, forecast, highlightedEventIds, layers["Fire Events"], layers["Forecast Corridor"], layers.Exposure, placeForEvent, selectedDetection, selectedEvent, verifying, viewerReady, visibleEvents]);

  // The scene renders on demand, so keep it ticking while any case marker pulses.
  const anyPulsing = useMemo(() => verifying.size > 0 || visibleEvents.some((e) => e.case?.evidence_checked && e.case.provisional && e.case.state !== "Ended"), [verifying, visibleEvents]);
  useEffect(() => {
    if (!anyPulsing || !layers["Fire Events"]) return;
    const timer = window.setInterval(() => viewerRef.current?.scene.requestRender(), 90);
    return () => window.clearInterval(timer);
  }, [anyPulsing, layers]);

  function applyCaseMarker(eventId: string, marker: CaseMarker) {
    setEvents((cur) => cur.map((e) => (e.event_id === eventId ? { ...e, case: marker } : e)));
  }

  // A detection opens a case at once: gather evidence for the strongest events without waiting for a click.
  // Runs once per data load; marker updates must not restart it.
  const candidateKey = useMemo(() => {
    const budget = AUTO_VERIFY_COUNT - loadBudgetUsedRef.current;
    if (!autoVerify || period === "historical" || budget <= 0) return "";
    // When scripted demo cases are on the map, verify only those; otherwise the strongest events.
    const pool = visibleEvents.some((e) => e.featured) ? visibleEvents.filter((e) => e.featured) : visibleEvents;
    return [...pool]
      .filter((e) => !e.case?.evidence_checked && !attemptedRef.current.has(e.event_id))
      .sort((a, b) => Number(Boolean(b.featured)) - Number(Boolean(a.featured)) || Number(highlightedEventIds.has(b.event_id)) - Number(highlightedEventIds.has(a.event_id)) || b.total_frp - a.total_frp)
      .slice(0, budget)
      .map((e) => e.event_id)
      .join(",");
  }, [autoVerify, period, visibleEvents, highlightedEventIds]);

  useEffect(() => {
    if (!candidateKey || verifyRunningRef.current) return;
    verifyRunningRef.current = true;
    const ids = candidateKey.split(",");
    ids.forEach((id) => attemptedRef.current.add(id));
    loadBudgetUsedRef.current += ids.length;
    (async () => {
      for (const [i, id] of ids.entries()) {
        if (unmountedRef.current || !autoVerifyRef.current) break;
        const e = eventsRef.current.find((x) => x.event_id === id);
        setVerifying((cur) => new Set(cur).add(id));
        setVerifyStatus(`Checking fire ${i + 1} of ${ids.length}${e ? `: ${placeForEvent[id] ?? `${e.centroid.lat.toFixed(2)}°, ${e.centroid.lon.toFixed(2)}°`}` : ""}`);
        try {
          const result = await runJob(
            startEvidence(id),
            (job) => {
              if (job.partial?.fire_case && !unmountedRef.current) applyCaseMarker(id, { ...job.partial.fire_case.marker, evidence_checked: true, updated_at: job.partial.updated_at });
            },
            unmountedRef.current ? { cancelled: true } : undefined,
          );
          if (!unmountedRef.current) applyCaseMarker(id, { ...result.fire_case.marker, evidence_checked: true, updated_at: result.generated_at });
        } catch {
          // A failed check leaves the marker hollow; the case can still be opened by clicking it.
        } finally {
          setVerifying((cur) => {
            const next = new Set(cur);
            next.delete(id);
            return next;
          });
        }
      }
      verifyRunningRef.current = false;
      if (!unmountedRef.current) setVerifyStatus(`Checked ${ids.length} fire${ids.length > 1 ? "s" : ""}. Click any circle to see what we found.`);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateKey]);

  function flyToBBox(b: [number, number, number, number]) {
    viewerRef.current?.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(b[0], b[1], b[2], b[3]), duration: 1.2 });
  }

  function zoom(direction: "in" | "out") {
    const camera = viewerRef.current?.camera;
    if (!camera) return;
    const amount = Math.max(camera.positionCartographic.height * 0.45, 60000);
    if (direction === "in") camera.zoomIn(amount);
    else camera.zoomOut(amount);
    viewerRef.current?.scene.requestRender();
  }

  async function runPlaceSearch(event: React.FormEvent) {
    event.preventDefault();
    if (placeQuery.trim().length < 2) return;
    placeRequest.current?.abort();
    const controller = new AbortController();
    placeRequest.current = controller;
    setPlaceSearchStatus("Finding boundaries...");
    try {
      const results = await searchPlaces(placeQuery.trim(), controller.signal);
      if (controller.signal.aborted) return;
      setPlaceResults(results);
      setPlaceSearchStatus(results.length ? null : "No places found. Try a more specific name.");
    } catch (error) {
      if (controller.signal.aborted) return;
      setPlaceSearchStatus(normalizeApiError(error));
    }
  }

  function choosePlace(p: PlaceResult) {
    if (!p.geometry || !["Polygon", "MultiPolygon"].includes(p.geometry.type)) {
      setPlaceSearchStatus("No administrative boundary available. Choose a country, region or district.");
      return;
    }
    setPlaceResults([]);
    placeRequest.current?.abort();
    setPlaceSearchStatus(null);
    const next: AOI = { id: p.place_id, geometry: p.geometry, bbox: p.bbox, name: p.place_name || p.name.split(",")[0], kind: "place" };
    setAoi(next);
    setFilterToAoi(true);
    setSearchOpen(false);
    flyToBBox(p.bbox);
  }

  function radiusAroundView() {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const center = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(viewer.canvas.clientWidth / 2, viewer.canvas.clientHeight / 2), viewer.scene.globe.ellipsoid);
    if (!center) return;
    const c = Cesium.Cartographic.fromCartesian(center);
    const lon = Cesium.Math.toDegrees(c.longitude);
    const lat = Cesium.Math.toDegrees(c.latitude);
    setAoi({ center: [lon, lat], radius_km: radiusKm, name: `${radiusKm} km around ${lat.toFixed(2)}, ${lon.toFixed(2)}`, kind: "radius" });
  }

  function finishDrawing() {
    if (drawPoints.length >= 3) {
      const ring = [...drawPoints, drawPoints[0]];
      setAoi({ geometry: { type: "Polygon", coordinates: [ring] }, name: "Custom polygon", kind: "polygon" });
    }
    setDrawPoints([]);
    setDrawing(false);
  }

  const behaviourCounts = (eventMeta.behaviour_counts ?? {}) as Record<string, number>;

  return (
    <section className={`cesium-shell command-globe fire-now ${themeClass(theme)} ${drawing ? "drawing" : ""} ${activeInsight ? "insight-open" : ""}`}>
      <div ref={containerRef} className="cesium-container" />
      <div className="mobile-map-controls">
        <button type="button" aria-expanded={mobilePanel === "filters"} aria-controls="map-filters" onClick={() => setMobilePanel(mobilePanel === "filters" ? null : "filters")}>{mobilePanel === "filters" ? "Close filters" : "Filters & place"}</button>
      </div>

      <nav className="insight-dock" aria-label="Data insights">
        {([
          { key: "snapshot", label: "At a glance" },
          { key: "intensity", label: "How strong" },
          { key: "timeline", label: "Last 24 hours" },
          { key: "events", label: "Biggest fires" },
        ] as const).map((o) => (
          <button
            key={o.key}
            type="button"
            className={activeInsight === o.key ? "active" : ""}
            onClick={() => setActiveInsight((cur) => (cur === o.key ? null : o.key))}
            aria-pressed={activeInsight === o.key}
          >
            {o.label}
          </button>
        ))}
      </nav>

      {activeInsight && (
        <aside className="insight-drawer" aria-label="Insight panel">
          <header>
            <div>
              <p className="mission-kicker">
                <span className="hud-dot" />{" "}
                {activeInsight === "snapshot" && "Live snapshot"}
                {activeInsight === "intensity" && "How strong are the fires?"}
                {activeInsight === "timeline" && "Satellite sightings · last 24 hours"}
                {activeInsight === "events" && "Biggest fires right now"}
              </p>
              <small className="insight-context">{periodLabels[period]}{period === "historical" ? ` · ${historicalDate}` : ""}</small>
            </div>
            <button type="button" className="insight-close" onClick={() => setActiveInsight(null)} aria-label="Close panel">×</button>
          </header>

          {activeInsight === "snapshot" && (
            <div className="insight-body snapshot-body">
              <div className="hud-stat">
                <span>Heat spots seen</span>
                <strong>{visibleHotspots.length.toLocaleString()}</strong>
                <small>MODIS {stats.modis.toLocaleString()} · VIIRS {stats.viirs.toLocaleString()}</small>
              </div>
              <div className="hud-stat tone-warn">
                <span>Seen by two satellite types</span>
                <strong>{stats.crossConfirmed.toLocaleString()}</strong>
                <small>Both MODIS and VIIRS, close in place and time</small>
              </div>
              <div className="hud-stat">
                <span>Separate fires</span>
                <strong>{stats.eventCount.toLocaleString()}</strong>
                <small>{Math.round(stats.eventArea).toLocaleString()} km² covered</small>
              </div>
              <div className="hud-stat tone-hot">
                <span>Strongest fire</span>
                <strong>{Math.round(stats.maxFrp).toLocaleString()}<i>MW</i></strong>
                <small>All fires together: {Math.round(stats.totalFrp).toLocaleString()} MW of heat</small>
              </div>
            </div>
          )}

          {activeInsight === "intensity" && (
            <div className="insight-body">
              <ul className="frp-bars">
                {(() => {
                  const total = Math.max(1, stats.weak + stats.mild + stats.strong + stats.intense);
                  const rows = [
                    { key: "Very strong", n: stats.intense, hint: "≥100 MW", color: "#b91c1c" },
                    { key: "Strong", n: stats.strong, hint: "30–100", color: "#ea580c" },
                    { key: "Medium", n: stats.mild, hint: "10–30", color: "#f59e0b" },
                    { key: "Weak", n: stats.weak, hint: "<10", color: "#fde68a" },
                  ];
                  return rows.map((r) => (
                    <li key={r.key}>
                      <em>{r.key}</em>
                      <div className="bar-track"><i style={{ width: `${(r.n / total) * 100}%`, background: r.color }} /></div>
                      <b>{r.n.toLocaleString()}</b>
                      <small>{r.hint}</small>
                    </li>
                  ));
                })()}
              </ul>
              <p className="insight-note">Fire power is the heat a fire gives off, in megawatts (MW). A cooking stove is about 0.002 MW; a large forest fire can exceed 100 MW per spot.</p>
            </div>
          )}

          {activeInsight === "timeline" && (
            <div className="insight-body">
              <div className="hud-sparkbars" aria-hidden="true">
                {stats.hours.map((n, i) => (
                  <div key={i} style={{ height: `${Math.max(6, (n / stats.hourMax) * 100)}%` }} title={`${n} detections`} />
                ))}
              </div>
              <ul className="axis-mini"><li>-24h</li><li>-12h</li><li>now</li></ul>
              <p className="insight-note">Each bar is two hours. The busiest two hours had {Math.max(...stats.hours).toLocaleString()} sightings. Bars rise when satellites pass over, not only when fires grow.</p>
            </div>
          )}

          {activeInsight === "events" && (
            <div className="insight-body">
              {stats.topEvents.length === 0 ? (
                <p className="hud-empty">No fire has been seen more than once yet.</p>
              ) : (
                <ul className="hud-events">
                  {stats.topEvents.map((e) => {
                    const color = BEHAVIOUR_COLORS[e.behaviour_state] ?? "#6ad7ff";
                    return (
                      <li key={e.event_id}>
                        <span className="hud-event-dot" style={{ background: color }} />
                        <div>
                          <strong>{placeForEvent[e.event_id] ?? `Fire near ${e.centroid.lat.toFixed(1)}°, ${e.centroid.lon.toFixed(1)}°`}</strong>
                          <em>{BEHAVIOUR_PLAIN[e.behaviour_state] ?? e.behaviour_state} · seen {e.observation_count} times</em>
                        </div>
                        <b>{e.observation_count}</b>
                      </li>
                    );
                  })}
                </ul>
              )}
              <ul className="behaviour-mini">
                {Object.entries(BEHAVIOUR_COLORS).map(([state, color]) => (
                  <li key={state}>
                    <i style={{ background: color }} />
                    <span>{BEHAVIOUR_PLAIN[state] ?? state}</span>
                    <b>{(stats.behaviour[state] ?? 0).toLocaleString()}</b>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      )}

      <aside id="map-filters" className={`scene-panel globe-left ${mobilePanel === "filters" ? "mobile-panel-open" : ""}`}>
        <section>
          <p className="panel-title">Fire Now</p>
          <p className="map-howto">Click a point for details.</p>
          <span className={`firms-badge ${feedState}`} role="status"><i />NASA FIRMS | {feedState === "loading" ? "Loading" : feedState === "live" ? "NRT available" : feedState === "partial" ? "Partial coverage" : feedState === "cached" ? "Cached observations" : feedState === "failed" ? "Unavailable" : "Observations loaded"}</span>
          <h3 className="filter-section-title">Time range</h3>
          <div className="option-grid">
            {(Object.keys(periodLabels) as Period[]).map((p) => (
              <button key={p} type="button" className={period === p ? "option-card active" : "option-card"} aria-pressed={period === p} onClick={() => setPeriod(p)}>{periodLabels[p]}</button>
            ))}
          </div>
          {period === "historical" && (
            <label className="select-row"><span>Date (UTC)</span><input type="date" value={historicalDate} max={new Date().toISOString().slice(0, 10)} min="2000-11-01" onChange={(e) => setHistoricalDate(e.target.value)} /></label>
          )}
          <button className="option-card refresh-live-data" type="button" disabled={feedState === "loading"} onClick={() => void loadData()}><RefreshCw size={14} aria-hidden="true" className={feedState === "loading" ? "is-spinning" : ""} />Refresh FIRMS</button>
          {lastRefresh && <p className="refresh-timestamp">Updated <time dateTime={lastRefresh}>{new Date(lastRefresh).toLocaleTimeString("en-GB", {timeZone: "UTC"})} UTC</time></p>}
        </section>
        <section className="harmonization-status" aria-live="polite" aria-busy={feedState === "loading"}>
          <p className={`processing-state ${feedState}`}>{feedState === "loading" ? "Loading..." : feedState === "failed" ? "Processing failed" : processingPending ? "Observations loaded. Matching events..." : period === "historical" ? "Historical observations loaded" : "Ready"}</p>
          {feedState === "loading" && <span className="processing-indicator" aria-label="Processing observations" />}
          {mergedCount !== null && <p className="merged-count"><strong>{mergedCount.toLocaleString()}</strong> total merged events</p>}
          {feedState === "failed" && <p className="refresh-timestamp">Data unavailable. Try Refresh FIRMS.</p>}
          <details className="sidebar-data-details">
            <summary>Data details</summary>
          <p className="tiles-status">{dataStatus}</p>
          {eventStatus && <p className="tiles-status">{eventStatus}</p>}
          {verifyStatus && <p className="tiles-status verify-status">{verifying.size > 0 && <span className="pulse-dot" />}{verifyStatus}</p>}
          </details>
        </section>
        <section>
          <p className="panel-title">Satellites</p>
          <div className="compact-layer-grid satellite-toggle-list">
            {satelliteLayers.map((platform) => {
              const count = satelliteCounts[platform];
              return <button key={platform} className={layers[platform] ? "active" : ""} type="button" aria-pressed={layers[platform]} onClick={() => setLayers(cur => toggleObservationLayer(cur, platform, satelliteLayers))}>
                <span className="layer-check" aria-hidden="true">{layers[platform] ? "\u2713" : ""}</span>
                <i className="sensor-dot" style={{ background: satelliteColors[platform] }} />
                <span className="satellite-name">{LAYER_LABEL[platform]}</span><span className="layer-count">{count.toLocaleString()}</span>
              </button>;
            })}
          </div>
          <div className="compact-layer-grid">
            <button className={layers.Harmonized ? "active" : ""} type="button" aria-pressed={layers.Harmonized} disabled={period === "historical"} onClick={() => setLayers(cur => toggleObservationLayer(cur, "Harmonized", satelliteLayers))}>Merged map points · {hotspots.filter((h) => h.harmonized && (!filterToAoi || !aoi || aoiContains(aoi, h.lat, h.lon))).length.toLocaleString()}</button>
          </div>
          {mergedCount !== null && <p className="refresh-timestamp">All merged events are loaded. Zoom in to separate overlapping points.</p>}
          <p className="panel-title">Overlays</p>
          <div className="compact-layer-grid">
            {(["Forecast Corridor", "Exposure", "Boundaries"] as LayerKey[]).map((layer) => (
              <button key={layer} className={layers[layer] ? "active" : ""} type="button" aria-pressed={layers[layer]} disabled={layer === "Forecast Corridor" ? !forecast.horizon : layer === "Exposure" ? exposure.length === 0 : false} title={layer === "Forecast Corridor" && !forecast.horizon ? "Select a fire and run its forecast first." : layer === "Exposure" && exposure.length === 0 ? "Select a fire and run its nearby analysis first." : undefined} onClick={() => setLayers((cur) => ({ ...cur, [layer]: !cur[layer] }))}>{LAYER_LABEL[layer]}</button>
            ))}
          </div>
          {layers["Fire Events"] && (
            <div className="behaviour-legend">
              {(Object.keys(KIND_COLORS) as Array<keyof typeof KIND_COLORS>).map((kind) => (
                <span key={kind}><i style={{ borderColor: KIND_COLORS[kind], background: kind === "unknown" ? "transparent" : KIND_COLORS[kind] }} />{KIND_LABELS[kind]}</span>
              ))}
              <label className="switch-row"><span>Check the {AUTO_VERIFY_COUNT} main fires automatically</span><input type="checkbox" checked={autoVerify} onChange={(e) => setAutoVerify(e.target.checked)} /></label>

              <small>
                What the fires are doing:{" "}
                {Object.keys(BEHAVIOUR_COLORS).filter((s) => behaviourCounts[s]).map((s) => `${(BEHAVIOUR_PLAIN[s] ?? s).toLowerCase()} ${behaviourCounts[s].toLocaleString()}`).join(" · ") || "none"}
              </small>
            </div>
          )}
        </section>
      </aside>
      {!lockedArea && <>
        <button type="button" className="floating-place-button" aria-label={drawing ? "Finish polygon" : searchOpen ? "Close location search" : "Search location"} aria-expanded={searchOpen} aria-controls="floating-place-search" onClick={() => drawing ? finishDrawing() : setSearchOpen(open => !open)}>
          {searchOpen ? <X size={18} aria-hidden="true" /> : <Search size={18} aria-hidden="true" />}<span>{drawing ? `Finish polygon (${drawPoints.length})` : "Search"}</span>
        </button>
        {searchOpen && <section id="floating-place-search" className="floating-place-search" aria-label="Location search" onKeyDown={e => { if (e.key === "Escape") { setSearchOpen(false); document.querySelector<HTMLButtonElement>(".floating-place-button")?.focus(); } }}>
          <header><p className="panel-title">Choose a place</p><button type="button" aria-label="Close search panel" onClick={() => setSearchOpen(false)}><X size={16} aria-hidden="true" /></button></header>
          <form className="aoi-search dark" onSubmit={runPlaceSearch}>
            <input autoFocus value={placeQuery} onChange={(e) => { placeRequest.current?.abort(); setPlaceQuery(e.target.value); setPlaceResults([]); setPlaceSearchStatus(null); if (!e.target.value.trim() && aoi?.kind === "place") { setAoi(null); setFilterToAoi(false); } }} placeholder="Country, city, forest..." aria-label="Search place" />
            <button type="submit">Go</button>
          </form>
          {placeSearchStatus && <p className="place-search-status" role="status">{placeSearchStatus}</p>}
          {placeResults.length > 0 && (
            <ul className="aoi-results dark">
              {placeResults.map((r) => (
                <li key={`${r.name}-${r.center.join(",")}`}><button type="button" onClick={() => choosePlace(r)}><strong>{r.name.split(",")[0]}</strong><span>{(r.addresstype || r.type).replace(/_/g, " ")}</span></button></li>
              ))}
            </ul>
          )}
          <div className="aoi-tools">
            <label className="select-row"><span>Radius km</span><input type="number" min={1} max={500} value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))} /></label>
            <button type="button" onClick={radiusAroundView}>Radius around view centre</button>
            {drawing ? (
              <button type="button" className="active" onClick={finishDrawing}>Finish polygon ({drawPoints.length} pts)</button>
            ) : (
              <button type="button" onClick={() => { setDrawing(true); setDrawPoints([]); setSearchOpen(false); }}>Draw polygon (click points)</button>
            )}
          </div>
          {aoi && (
            <div className="aoi-current">
              <strong>{describeAoi(aoi)}</strong>
              <label className="switch-row"><span>Show only this area</span><input type="checkbox" checked={filterToAoi} onChange={(e) => setFilterToAoi(e.target.checked)} /></label>
              <div className="aoi-actions">
                <button type="button" onClick={() => flyToBBox(aoiBBox(aoi)!)}>Zoom</button>
                <Link to="/fire-calendar">Fire Memory →</Link>
                <button type="button" onClick={() => setAoi(null)}>Clear</button>
              </div>
            </div>
          )}
        </section>}
      </>}
      {viewerError && (
        <div className="cesium-error-panel">
          <h3>3D map could not start</h3>
          <p>{viewerError}</p>
        </div>
      )}
      {drawing && <div className="draw-hint">Click on the globe to add polygon points, then press "Finish polygon".</div>}
      {selectionStatus && !selectedFire && <div className="selection-status">{selectionStatus}</div>}
      {feedState !== "loading" && visibleHotspots.length === 0 && (!layers["Fire Events"] || visibleEvents.length === 0) && !viewerError && <div className="map-empty-state" role="status"><strong>{feedState === "failed" ? "Observations unavailable" : "No observations to display"}</strong><span>{feedState === "failed" ? "Refresh FIRMS to retry the data request." : "Try another date, place or satellite layer. No detections does not establish absence of fire."}</span></div>}
      <div className="zoom-controls" aria-label="Map zoom controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoom("in")}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoom("out")}>{"\u2212"}</button>
        <button type="button" aria-label="Reset globe view" title="Reset view" onClick={() => viewerRef.current?.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(locations["Atlantic View"].lon, locations["Atlantic View"].lat, locations["Atlantic View"].height), orientation: nadirOrientation, duration: 1.2 })}><RotateCcw size={17} aria-hidden="true" /></button>
      </div>
      {selectedFire && (
        <Suspense fallback={<div className="event-panel-loading" role="status">Loading fire details…</div>}>
        <EventPanel
          event={selectedEvent}
          detection={selectedDetection}
          selectionStatus={selectionStatus}
          onClose={() => { selectionSequence.current += 1; setSelectedFire(null); setSelectionStatus(null); setForecast({ horizon: null, size: 0 }); setExposure([]); }}
          onForecast={(horizon, size) => setForecast({ horizon, size })}
          onExposure={setExposure}
          onCaseUpdate={applyCaseMarker}
        />
        </Suspense>
      )}
    </section>
  );
}
