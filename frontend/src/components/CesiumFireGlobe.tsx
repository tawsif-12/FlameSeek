import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { getCurrentHotspots, getEvent, getEvents, lookupEvent, normalizeApiError, searchPlaces } from "../api/client";
import { DEFAULT_SENSORS, aoiBBox, aoiContains, describeAoi, useAppContext } from "../context/AppContext";
import type { AOI, FireEvent, FireEventSummary, ForecastHorizon, HotspotRecord, PlaceResult } from "../types/api";
import EventPanel, { BEHAVIOUR_COLORS } from "./EventPanel";

type LayerKey = "MODIS" | "VIIRS" | "Fire Events" | "FRP Columns" | "Forecast Corridor" | "Exposure";
type LightingMode = "Dawn" | "Day" | "Dusk" | "Night";
type ThemeMode = "Default" | "Faded" | "Mono" | "Ocean" | "Warm" | "Vivid";
type EarthMode = "Map" | "3D Terrain" | "Photorealistic";
type Period = "1" | "2" | "5" | "historical";
type ExposureMarker = { lat: number; lon: number; name: string; category: string };

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

const layerDefaults: Record<LayerKey, boolean> = { MODIS: true, VIIRS: true, "Fire Events": true, "FRP Columns": false, "Forecast Corridor": true, Exposure: true };
const lightingModes: LightingMode[] = ["Dawn", "Day", "Dusk", "Night"];
const themeModes: ThemeMode[] = ["Default", "Faded", "Mono", "Ocean", "Warm", "Vivid"];
const periodLabels: Record<Period, string> = { "1": "Last 24 h", "2": "Last 48 h", "5": "Last 5 days", historical: "Historical date" };
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
  return `hs:${h.sensor}|${h.lat}|${h.lon}|${h.acq_datetime}`;
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
    if (confirmed.has(hotspotKey(h))) return Cesium.Color.RED.withAlpha(0.95);
    return h.sensor === "modis" ? Cesium.Color.LIME.withAlpha(0.95) : Cesium.Color.YELLOW.withAlpha(0.95);
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
  viewer.entities.values.forEach((entity) => {
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
    return aoi.geometry.type === "Polygon" ? (aoi.geometry.coordinates as number[][][])[0] : (aoi.geometry.coordinates as number[][][][]).sort((a, b) => b[0].length - a[0].length)[0][0];
  }
  const b = aoiBBox(aoi)!;
  return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];
}

export default function CesiumFireGlobe() {
  const { aoi, setAoi } = useAppContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(layerDefaults);
  const [selectedLocation, setSelectedLocation] = useState<keyof typeof locations>("Atlantic View");
  const [lighting, setLighting] = useState<LightingMode>("Day");
  const [theme, setTheme] = useState<ThemeMode>("Default");
  const [showImagery, setShowImagery] = useState(true);
  const [earthMode, setEarthMode] = useState<EarthMode>("3D Terrain");
  const [sensorColors, setSensorColors] = useState(true);
  const [showBuildings, setShowBuildings] = useState(true);
  const [tilesStatus, setTilesStatus] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("1");
  const [historicalDate, setHistoricalDate] = useState(() => new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10));
  const [hotspots, setHotspots] = useState<HotspotRecord[]>([]);
  const [events, setEvents] = useState<FireEventSummary[]>([]);
  const [eventMeta, setEventMeta] = useState<Record<string, unknown>>({});
  const [dataStatus, setDataStatus] = useState("Loading live FIRMS MODIS/VIIRS data...");
  const [eventStatus, setEventStatus] = useState<string | null>(null);
  const [filterToAoi, setFilterToAoi] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [drawPoints, setDrawPoints] = useState<number[][]>([]);
  const [placeQuery, setPlaceQuery] = useState("");
  const [placeResults, setPlaceResults] = useState<PlaceResult[]>([]);
  const [radiusKm, setRadiusKm] = useState(50);
  const [selectedEvent, setSelectedEvent] = useState<FireEvent | null>(null);
  const [selectedDetection, setSelectedDetection] = useState<HotspotRecord | null>(null);
  const [selectionStatus, setSelectionStatus] = useState<string | null>(null);
  const [forecast, setForecast] = useState<{ horizon: ForecastHorizon | null; size: number }>({ horizon: null, size: 0 });
  const [exposure, setExposure] = useState<ExposureMarker[]>([]);
  const [viewerReady, setViewerReady] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [activeInsight, setActiveInsight] = useState<null | "snapshot" | "intensity" | "timeline" | "events">(null);
  const buildingsRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const photorealisticTilesRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const photorealisticLoadingRef = useRef(false);
  const terrainRef = useRef<Cesium.TerrainProvider | null>(null);
  const ellipsoidTerrainRef = useRef<Cesium.EllipsoidTerrainProvider | null>(null);
  const lookupRef = useRef<Map<string, HotspotRecord>>(new Map());
  const drawingRef = useRef(false);
  const removeCameraOcclusionRef = useRef<Cesium.Event.RemoveCallback | null>(null);

  const visibleHotspots = useMemo(
    () => hotspots.filter((h) => layers[sensorFamily(h.sensor) as "MODIS" | "VIIRS"] && (!filterToAoi || !aoi || aoiContains(aoi, h.lat, h.lon))),
    [hotspots, layers, filterToAoi, aoi],
  );
  const visibleEvents = useMemo(
    () => events.filter((e) => e.observation_count >= 3 && (!filterToAoi || !aoi || aoiContains(aoi, e.centroid.lat, e.centroid.lon))),
    [events, filterToAoi, aoi],
  );
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
    }
    return lookup;
  }, [events, hotspots]);

  const stats = useMemo(() => {
    const modis = visibleHotspots.filter((h) => h.sensor === "modis").length;
    const viirs = visibleHotspots.length - modis;
    const crossConfirmed = visibleHotspots.filter((h) => confirmed.has(hotspotKey(h))).length;
    const frps = visibleHotspots.map((h) => h.frp ?? 0);
    const totalFrp = frps.reduce((s, v) => s + v, 0);
    const maxFrp = frps.length ? Math.max(...frps) : 0;
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

  async function loadData() {
    const historical = period === "historical";
    const days = historical ? 1 : Number(period);
    setDataStatus(historical ? `Loading archived detections for ${historicalDate}...` : `Loading FIRMS detections (${periodLabels[period].toLowerCase()})...`);
    try {
      const response = await getCurrentHotspots(DEFAULT_SENSORS, days, 4000, historical ? historicalDate : undefined);
      setHotspots(response.hotspots);
      const m = response.metadata as Record<string, number | string>;
      setDataStatus(
        `${historical ? `Archive ${historicalDate}` : periodLabels[period]}: ${Number(m.filtered_hotspot_count).toLocaleString()} detections, showing the ${Number(m.returned_hotspot_count).toLocaleString()} strongest by FRP.`,
      );
    } catch (error) {
      setHotspots([]);
      setDataStatus(`FIRMS unavailable: ${normalizeApiError(error)}`);
    }
    if (historical) {
      setEvents([]);
      setEventStatus("Event reconstruction runs on recent data. Use Fire Memory for historical events in an area.");
      return;
    }
    setEventStatus("Reconstructing fire events...");
    try {
      const response = await getEvents(Math.max(2, days));
      setEvents(response.events);
      setEventMeta(response.metadata);
      setEventStatus(`${Number(response.metadata.multi_detection_events).toLocaleString()} multi-detection events from ${Number(response.metadata.detections).toLocaleString()} detections.`);
    } catch (error) {
      setEvents([]);
      setEventStatus(`Event reconstruction unavailable: ${normalizeApiError(error)}`);
    }
  }

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

  async function openEvent(eventId: string, detection: HotspotRecord | null) {
    setSelectionStatus("Loading fire event...");
    try {
      const ev = await getEvent(eventId);
      setSelectedEvent(ev);
      setSelectedDetection(detection);
      setSelectionStatus(null);
    } catch (error) {
      setSelectionStatus(normalizeApiError(error));
    }
  }

  async function openDetection(h: HotspotRecord) {
    setSelectionStatus(h.place_hint
      ? `${h.place_hint} · loading fire event…`
      : "Finding the fire event this detection belongs to...");
    try {
      const eventId = await lookupEvent(h.sensor, h.lat, h.lon, h.acq_datetime);
      await openEvent(eventId, h);
    } catch (error) {
      setSelectionStatus(`${normalizeApiError(error)} Historical-date detections are not linked into events.`);
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
        const worldImageryProvider = cesiumIonToken
          ? await Cesium.createWorldImageryAsync({ style: Cesium.IonWorldImageryStyle.AERIAL })
          : await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"));

        const viewer = new Cesium.Viewer(containerRef.current, {
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
        viewer.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

        viewer.selectedEntityChanged.addEventListener((entity) => {
          if (drawingRef.current || !entity) return;
          const id = String(entity.id);
          if (id.startsWith("hs:")) {
            const h = lookupRef.current.get(id.split("#")[0]);
            if (h) void openDetection(h);
          } else if (id.startsWith("ev:")) {
            void openEvent(id.slice(3).split("#")[0], null);
          }
        });

        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
          if (!drawingRef.current) return;
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
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString(daylightBackgrounds.Day);
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.saturationShift = -0.55;
          viewer.scene.skyAtmosphere.brightnessShift = -0.15;
        }
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
      buildingsRef.current = null;
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
      setSearchParams({ event: selectedEvent.event_id }, { replace: true });
    } else if (hadEventRef.current) {
      // Only clear the link when the user closes an open event, not before a linked one loads.
      hadEventRef.current = false;
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEvent]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString(daylightBackgrounds[lighting]);
    viewer.scene.requestRender();
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
    if (!viewer) return;
    if (earthMode === "Photorealistic") void loadPhotorealisticTiles(viewer);
    const terrainProvider = earthMode === "Map" ? ellipsoidTerrainRef.current : terrainRef.current;
    if (terrainProvider) viewer.terrainProvider = terrainProvider;
    configureCameraController(viewer, earthMode);
    viewer.scene.globe.show = earthMode !== "Photorealistic" || !photorealisticTilesRef.current;
    viewer.scene.requestRender();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [earthMode, viewerReady]);

  // Rebuild all overlay entities whenever data, layers, AOI or selection change.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.entities.removeAll();
    lookupRef.current = new Map();

    visibleHotspots.forEach((h) => {
      const id = hotspotKey(h);
      lookupRef.current.set(id, h);
      const isHighlighted = highlightRegion && isHighlightedHotspot(h);
      const color = isHighlighted ? HIGHLIGHT_COLOR : hotspotColor(h, confirmed, sensorColors);
      const basePx = h.sensor === "modis" ? 9 : 7;
      const entityName = h.place_hint
        ? `${sensorFamily(h.sensor)} · ${h.place_hint}`
        : `${sensorFamily(h.sensor)} detection`;
      viewer.entities.add({
        id,
        name: entityName,
        position: Cesium.Cartesian3.fromDegrees(h.lon, h.lat, 0),
        point: {
          pixelSize: isHighlighted ? basePx + 4 : basePx,
          color,
          outlineColor: isHighlighted ? HIGHLIGHT_COLOR.withAlpha(0.8) : Cesium.Color.BLACK.withAlpha(0.6),
          outlineWidth: isHighlighted ? 3 : 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: 0,
        },
        cylinder: layers["FRP Columns"]
          ? { length: Math.max(8000, (h.frp ?? 1) * 1500), topRadius: 9000, bottomRadius: 9000, material: color.withAlpha(0.4), heightReference: Cesium.HeightReference.CLAMP_TO_GROUND }
          : undefined,
      });
    });

    if (layers["Fire Events"]) {
      visibleEvents.forEach((e) => {
        const baseColor = Cesium.Color.fromCssColorString(BEHAVIOUR_COLORS[e.behaviour_state] ?? "#e2e8f0");
        const selected = selectedEvent?.event_id === e.event_id;
        const isHighlighted = highlightedEventIds.has(e.event_id);
        const placeLabel = placeForEvent[e.event_id];
        const color = isHighlighted ? HIGHLIGHT_COLOR : baseColor;
        viewer.entities.add({
          id: `ev:${e.event_id}`,
          name: placeLabel ? `${placeLabel} · ${e.behaviour_state}` : `Fire event (${e.behaviour_state})`,
          position: Cesium.Cartesian3.fromDegrees(e.centroid.lon, e.centroid.lat, 0),
          point: {
            pixelSize: Math.min(24, 8 + Math.log2(e.observation_count) * 2) + (isHighlighted ? 4 : 0),
            color: color.withAlpha(isHighlighted ? 0.45 : 0.25),
            outlineColor: color,
            outlineWidth: isHighlighted ? 5 : selected ? 4 : 2,
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

    if (aoi) {
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
  }, [aoi, confirmed, drawPoints, exposure, forecast, highlightRegion, highlightedEventIds, layers, placeForEvent, selectedEvent, sensorColors, viewerReady, visibleEvents, visibleHotspots]);

  function flyToBBox(b: [number, number, number, number]) {
    viewerRef.current?.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(b[0], b[1], b[2], b[3]), duration: 1.2 });
  }

  function flyToLocation(name: keyof typeof locations) {
    setSelectedLocation(name);
    const d = locations[name];
    viewerRef.current?.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(d.lon, d.lat, name === "Atlantic View" || earthMode === "Map" ? d.height : Math.min(d.height, 1250000)),
      orientation: name === "Atlantic View" || earthMode === "Map" ? nadirOrientation : obliqueOrientation,
      duration: 1.2,
    });
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
    try {
      setPlaceResults(await searchPlaces(placeQuery.trim()));
    } catch (error) {
      setSelectionStatus(normalizeApiError(error));
    }
  }

  function choosePlace(p: PlaceResult) {
    setPlaceResults([]);
    const next: AOI = p.geometry ? { geometry: p.geometry, bbox: p.bbox, name: p.name.split(",").slice(0, 2).join(","), kind: "place" } : { bbox: p.bbox, name: p.name, kind: "place" };
    setAoi(next);
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
    <section className={`cesium-shell command-globe ${themeClass(theme)} ${drawing ? "drawing" : ""} ${activeInsight ? "insight-open" : ""}`}>
      <div ref={containerRef} className="cesium-container" />

      <nav className="insight-dock" aria-label="Data insights">
        {([
          { key: "snapshot", label: "Snapshot" },
          { key: "intensity", label: "FRP Mix" },
          { key: "timeline", label: "24 h Timeline" },
          { key: "events", label: "Top Events" },
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
                {activeInsight === "intensity" && "FRP intensity mix"}
                {activeInsight === "timeline" && "Detections · last 24 h"}
                {activeInsight === "events" && "Top active events"}
              </p>
              <small className="insight-context">{periodLabels[period]}{period === "historical" ? ` · ${historicalDate}` : ""}</small>
            </div>
            <button type="button" className="insight-close" onClick={() => setActiveInsight(null)} aria-label="Close panel">×</button>
          </header>

          {activeInsight === "snapshot" && (
            <div className="insight-body snapshot-body">
              <div className="hud-stat">
                <span>Detections</span>
                <strong>{visibleHotspots.length.toLocaleString()}</strong>
                <small>MODIS {stats.modis.toLocaleString()} · VIIRS {stats.viirs.toLocaleString()}</small>
              </div>
              <div className="hud-stat tone-warn">
                <span>Cross-confirmed</span>
                <strong>{stats.crossConfirmed.toLocaleString()}</strong>
                <small>MODIS ∩ VIIRS within 15 km / 6 h</small>
              </div>
              <div className="hud-stat">
                <span>Fire events</span>
                <strong>{stats.eventCount.toLocaleString()}</strong>
                <small>{Math.round(stats.eventArea).toLocaleString()} km² footprint</small>
              </div>
              <div className="hud-stat tone-hot">
                <span>Peak FRP</span>
                <strong>{Math.round(stats.maxFrp).toLocaleString()}<i>MW</i></strong>
                <small>Total {Math.round(stats.totalFrp).toLocaleString()} MW</small>
              </div>
            </div>
          )}

          {activeInsight === "intensity" && (
            <div className="insight-body">
              <ul className="frp-bars">
                {(() => {
                  const total = Math.max(1, stats.weak + stats.mild + stats.strong + stats.intense);
                  const rows = [
                    { key: "Intense", n: stats.intense, hint: "≥100 MW", color: "#b91c1c" },
                    { key: "Strong", n: stats.strong, hint: "30–100", color: "#ea580c" },
                    { key: "Mild", n: stats.mild, hint: "10–30", color: "#f59e0b" },
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
              <p className="insight-note">Distribution of visible detections by Fire Radiative Power.</p>
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
              <p className="insight-note">12 bins × 2 h each. Peak bin: {Math.max(...stats.hours).toLocaleString()} detections.</p>
            </div>
          )}

          {activeInsight === "events" && (
            <div className="insight-body">
              {stats.topEvents.length === 0 ? (
                <p className="hud-empty">No multi-detection events yet.</p>
              ) : (
                <ul className="hud-events">
                  {stats.topEvents.map((e) => {
                    const color = BEHAVIOUR_COLORS[e.behaviour_state] ?? "#6ad7ff";
                    return (
                      <li key={e.event_id}>
                        <span className="hud-event-dot" style={{ background: color }} />
                        <div>
                          <strong>EV-{e.event_id.slice(-6).toUpperCase()}</strong>
                          <em>{e.centroid.lat.toFixed(2)}°, {e.centroid.lon.toFixed(2)}° · {e.behaviour_state}</em>
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
                    <span>{state}</span>
                    <b>{(stats.behaviour[state] ?? 0).toLocaleString()}</b>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      )}

      <aside className="scene-panel globe-left">
        <section>
          <p className="panel-title">Fire Now · time period</p>
          <div className="option-grid">
            {(Object.keys(periodLabels) as Period[]).map((p) => (
              <button key={p} type="button" className={period === p ? "option-card active" : "option-card"} onClick={() => setPeriod(p)}>{periodLabels[p]}</button>
            ))}
          </div>
          {period === "historical" && (
            <label className="select-row"><span>Date (UTC)</span><input type="date" value={historicalDate} max={new Date().toISOString().slice(0, 10)} min="2000-11-01" onChange={(e) => setHistoricalDate(e.target.value)} /></label>
          )}
          <button className="option-card refresh-live-data" type="button" onClick={loadData}>Refresh FIRMS</button>
          <p className="tiles-status">{dataStatus}</p>
          {eventStatus && <p className="tiles-status">{eventStatus}</p>}
        </section>
        <section>
          <p className="panel-title">Layers</p>
          <div className="compact-layer-grid">
            {(Object.keys(layerDefaults) as LayerKey[]).map((layer) => (
              <button key={layer} className={layers[layer] ? "active" : ""} type="button" onClick={() => setLayers((cur) => ({ ...cur, [layer]: !cur[layer] }))}>{layer}</button>
            ))}
          </div>
          <label className="switch-row"><span>Sensor colours</span><input type="checkbox" checked={sensorColors} onChange={(e) => setSensorColors(e.target.checked)} /></label>
          <p className="tiles-status">{sensorColors ? "Green MODIS · yellow VIIRS · red = MODIS+VIIRS within 15 km / 6 h" : "Colour by FRP: pale < 10, amber 10–30, orange 30–100, red ≥ 100 MW"}</p>
          {layers["Fire Events"] && (
            <div className="behaviour-legend">
              {Object.entries(BEHAVIOUR_COLORS).map(([state, color]) => (
                <span key={state}><i style={{ borderColor: color }} />{state}{behaviourCounts[state] ? ` ${behaviourCounts[state].toLocaleString()}` : ""}</span>
              ))}
              <small>Events with 3+ detections are outlined. Click one to open it. States are inferred.</small>
            </div>
          )}
        </section>
        <section>
          <p className="panel-title">Area of interest</p>
          <form className="aoi-search dark" onSubmit={runPlaceSearch}>
            <input value={placeQuery} onChange={(e) => setPlaceQuery(e.target.value)} placeholder="Country, state, district, forest..." aria-label="Search place" />
            <button type="submit">Go</button>
          </form>
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
              <button type="button" onClick={() => { setDrawing(true); setDrawPoints([]); }}>Draw polygon (click points)</button>
            )}
          </div>
          {aoi && (
            <div className="aoi-current">
              <strong>{describeAoi(aoi)}</strong>
              {highlightRegion && <small className="aoi-demo-hint">✦ Active industrial clusters highlighted. Click one to see the place and open evidence.</small>}
              <label className="switch-row"><span>Show only this area</span><input type="checkbox" checked={filterToAoi} onChange={(e) => setFilterToAoi(e.target.checked)} /></label>
              <div className="aoi-actions">
                <button type="button" onClick={() => flyToBBox(aoiBBox(aoi)!)}>Zoom</button>
                <Link to="/fire-memory">Fire Memory →</Link>
                <button type="button" onClick={() => setAoi(null)}>Clear</button>
              </div>
            </div>
          )}
        </section>
      </aside>
      <aside className="control-panel-3d">
        <section>
          <p className="panel-title">Lighting</p>
          <div className="option-grid">
            {lightingModes.map((mode) => (
              <button key={mode} className={lighting === mode ? "option-card active" : "option-card"} type="button" onClick={() => setLighting(mode)}>
                <span>{mode === "Day" ? "SUN" : mode === "Night" ? "MOON" : "LIT"}</span>
                {mode}
              </button>
            ))}
          </div>
        </section>
        <section>
          <p className="panel-title">Color Theme</p>
          <div className="theme-grid">
            {themeModes.map((mode) => (
              <button key={mode} className={theme === mode ? "theme-card active" : "theme-card"} type="button" onClick={() => setTheme(mode)}>
                <span className={`theme-dots ${themeClass(mode)}`} />
                {mode}
              </button>
            ))}
          </div>
        </section>
        <section>
          <p className="panel-title">View</p>
          <div className="mode-toggle" aria-label="Earth display mode">
            {(["Map", "3D Terrain", "Photorealistic"] as EarthMode[]).map((mode) => (
              <button key={mode} className={earthMode === mode ? "active" : ""} type="button" onClick={() => setEarthMode(mode)}>{mode}</button>
            ))}
          </div>
          <label className="switch-row"><span>Imagery</span><input type="checkbox" checked={showImagery} onChange={(e) => setShowImagery(e.target.checked)} /></label>
          <label className="switch-row">
            <span>OSM Buildings</span>
            <input type="checkbox" checked={earthMode === "3D Terrain" && showBuildings} disabled={earthMode !== "3D Terrain"} onChange={(e) => setShowBuildings(e.target.checked)} />
          </label>
          {tilesStatus && <p className="tiles-status">{tilesStatus}</p>}
          <label className="select-row">
            <span>Location</span>
            <select value={selectedLocation} onChange={(e) => flyToLocation(e.target.value as keyof typeof locations)}>
              {Object.keys(locations).map((name) => <option key={name}>{name}</option>)}
            </select>
          </label>
        </section>
      </aside>
      {viewerError && (
        <div className="cesium-error-panel">
          <h3>3D map could not start</h3>
          <p>{viewerError}</p>
        </div>
      )}
      {drawing && <div className="draw-hint">Click on the globe to add polygon points, then press "Finish polygon".</div>}
      {selectionStatus && <div className="selection-status">{selectionStatus}</div>}
      <div className="zoom-controls" aria-label="Map zoom controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoom("in")}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoom("out")}>-</button>
      </div>
      {selectedEvent && (
        <EventPanel
          event={selectedEvent}
          detection={selectedDetection}
          onClose={() => { setSelectedEvent(null); setForecast({ horizon: null, size: 0 }); setExposure([]); }}
          onForecast={(horizon, size) => setForecast({ horizon, size })}
          onExposure={setExposure}
        />
      )}
    </section>
  );
}
