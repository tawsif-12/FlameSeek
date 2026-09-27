import { useEffect, useMemo, useRef, useState } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { getCurrentHotspots, getHotspotEvidence, normalizeApiError } from "../api/client";
import { DEFAULT_SENSORS } from "../context/AppContext";
import type { HotspotEvidenceResponse, HotspotRecord, SensorName } from "../types/api";

type FireSensor = "MODIS" | "VIIRS";
type LayerKey = FireSensor | "Harmonized Activity" | "Anomaly Layer";
type LightingMode = "Dawn" | "Day" | "Dusk" | "Night";
type ThemeMode = "Default" | "Faded" | "Mono" | "Ocean" | "Warm" | "Vivid";
type EarthMode = "Map" | "3D Terrain" | "Photorealistic";
type GlobeHotspot = {
  id: string;
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  satellite: string;
  sensor: FireSensor;
  confidence: string;
  frp: number | null;
  day_night: "D" | "N";
  grid_id: string;
  harmonized_activity_index: number;
  anomaly_score: number;
  cross_sensor_confirmed?: boolean;
  merge_distance_km?: number;
  merge_time_minutes?: number;
};

const daylightBackgrounds: Record<LightingMode, string> = {
  Dawn: "#061f36",
  Day: "#031529",
  Dusk: "#071a30",
  Night: "#020817",
};

const globeBaseColor = Cesium.Color.fromCssColorString("#0b2f63");

const defaultImageryStyle = {
  alpha: 1,
  brightness: 1,
  contrast: 1.02,
  gamma: 1,
  hue: 0,
  saturation: 1,
};

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

const nadirOrientation = {
  heading: 0,
  pitch: Cesium.Math.toRadians(-90),
  roll: 0,
};

const obliqueOrientation = {
  heading: Cesium.Math.toRadians(18),
  pitch: Cesium.Math.toRadians(-52),
  roll: 0,
};

const layerDefaults: Record<LayerKey, boolean> = {
  MODIS: true,
  VIIRS: true,
  "Harmonized Activity": true,
  "Anomaly Layer": true,
};

const lightingModes: LightingMode[] = ["Dawn", "Day", "Dusk", "Night"];
const themeModes: ThemeMode[] = ["Default", "Faded", "Mono", "Ocean", "Warm", "Vivid"];

const sceneItems = [
  { title: "Globe View", detail: "Rotating 3D fire globe" },
  { title: "Markers", detail: "MODIS and VIIRS detections" },
  { title: "Harmonized Overlay", detail: "Sensor-aware activity layer" },
  { title: "Activity Columns", detail: "FRP and anomaly height" },
  { title: "AOI Focus", detail: "Turn-by-turn location guidance" },
];

function formatTime(value: string) {
  return `${value.slice(0, 2)}:${value.slice(2)}`;
}

function statusForZ(z: number) {
  if (z >= 3) return "Very unusual";
  if (z >= 2) return "Unusual";
  if (z >= 1) return "Elevated";
  return "Normal";
}

function colorForHotspot(hotspot: GlobeHotspot, layers: Record<LayerKey, boolean>, useSensorConfirmationColors: boolean) {
  if (useSensorConfirmationColors) {
    if (hotspot.cross_sensor_confirmed) return Cesium.Color.RED.withAlpha(0.95);
    return hotspot.sensor === "MODIS" ? Cesium.Color.LIME.withAlpha(0.95) : Cesium.Color.YELLOW.withAlpha(0.95);
  }
  if (layers["Anomaly Layer"] && hotspot.anomaly_score >= 3) return Cesium.Color.MAGENTA.withAlpha(0.95);
  if (layers["Anomaly Layer"] && hotspot.anomaly_score >= 2) return Cesium.Color.RED.withAlpha(0.95);
  if (layers["Harmonized Activity"]) return Cesium.Color.ORANGE.withAlpha(0.9);
  return hotspot.sensor === "VIIRS" ? Cesium.Color.CYAN.withAlpha(0.9) : Cesium.Color.YELLOW.withAlpha(0.9);
}

function sensorFamily(sensor: HotspotRecord["sensor"]): FireSensor {
  return sensor === "modis" ? "MODIS" : "VIIRS";
}

function sensorNameForHotspot(hotspot: GlobeHotspot): SensorName {
  if (hotspot.sensor === "MODIS") return "modis";
  if (hotspot.satellite.toLowerCase().includes("noaa-20")) return "viirs_noaa20";
  if (hotspot.satellite.toLowerCase().includes("noaa-21")) return "viirs_noaa21";
  return "viirs_snpp";
}

function hotspotToEvidencePayload(hotspot: GlobeHotspot, refresh = false): HotspotRecord & { refresh?: boolean } {
  return {
    lat: hotspot.latitude,
    lon: hotspot.longitude,
    acq_datetime: `${hotspot.acq_date}T${formatTime(hotspot.acq_time)}:00Z`,
    confidence_pct: hotspot.confidence === "High" ? 90 : hotspot.confidence === "Nominal" ? 60 : Number.parseFloat(hotspot.confidence) || 0,
    frp: hotspot.frp,
    sensor: sensorNameForHotspot(hotspot),
    satellite: hotspot.satellite,
    daynight: hotspot.day_night,
    refresh,
  };
}

function timeFromIso(value: string) {
  const date = new Date(value);
  return `${String(date.getUTCHours()).padStart(2, "0")}${String(date.getUTCMinutes()).padStart(2, "0")}`;
}

function liveHotspotToGlobeHotspot(record: HotspotRecord, index: number): GlobeHotspot {
  const date = new Date(record.acq_datetime);
  const confidence = record.confidence_pct >= 80 ? "High" : record.confidence_pct >= 50 ? "Nominal" : `${record.confidence_pct.toFixed(0)}%`;
  const frp = record.frp ?? 0;
  return {
    id: `live-${record.sensor}-${index}-${record.lat.toFixed(4)}-${record.lon.toFixed(4)}-${record.acq_datetime}`,
    latitude: record.lat,
    longitude: record.lon,
    acq_date: date.toISOString().slice(0, 10),
    acq_time: timeFromIso(record.acq_datetime),
    satellite: record.satellite || record.sensor.toUpperCase(),
    sensor: sensorFamily(record.sensor),
    confidence,
    frp: record.frp,
    day_night: record.daynight === "N" ? "N" : "D",
    grid_id: `${record.lat.toFixed(2)}_${record.lon.toFixed(2)}`,
    harmonized_activity_index: Math.max(0.4, Math.min(4, frp / 20)),
    anomaly_score: Math.max(0.4, Math.min(4, frp / 15)),
  };
}

function hotspotTimestamp(hotspot: GlobeHotspot) {
  return new Date(`${hotspot.acq_date}T${formatTime(hotspot.acq_time)}:00Z`).getTime();
}

function distanceKm(a: GlobeHotspot, b: GlobeHotspot) {
  const radiusKm = 6371;
  const lat1 = Cesium.Math.toRadians(a.latitude);
  const lat2 = Cesium.Math.toRadians(b.latitude);
  const deltaLat = Cesium.Math.toRadians(b.latitude - a.latitude);
  const deltaLon = Cesium.Math.toRadians(b.longitude - a.longitude);
  const sinLat = Math.sin(deltaLat / 2);
  const sinLon = Math.sin(deltaLon / 2);
  const h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon;
  return radiusKm * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function markCrossSensorConfirmed(hotspots: GlobeHotspot[]) {
  const maxDistanceKm = 15;
  const maxTimeMinutes = 360;
  const modis = hotspots.filter((hotspot) => hotspot.sensor === "MODIS");
  const viirs = hotspots.filter((hotspot) => hotspot.sensor === "VIIRS");

  return hotspots.map((hotspot) => ({
    ...hotspot,
    ...nearestOppositeSensorConfirmation(hotspot, hotspot.sensor === "MODIS" ? viirs : modis, maxDistanceKm, maxTimeMinutes),
  }));
}

function nearestOppositeSensorConfirmation(hotspot: GlobeHotspot, candidates: GlobeHotspot[], maxDistanceKm: number, maxTimeMinutes: number) {
  let best: { distance: number; minutes: number } | null = null;
  const hotspotTime = hotspotTimestamp(hotspot);
  for (const candidate of candidates) {
    const minutes = Math.abs(hotspotTime - hotspotTimestamp(candidate)) / 60000;
    if (minutes > maxTimeMinutes) continue;
    const distance = distanceKm(hotspot, candidate);
    if (distance > maxDistanceKm) continue;
    if (!best || distance < best.distance || (distance === best.distance && minutes < best.minutes)) {
      best = { distance, minutes };
    }
  }
  return {
    cross_sensor_confirmed: Boolean(best),
    merge_distance_km: best ? Number(best.distance.toFixed(1)) : undefined,
    merge_time_minutes: best ? Math.round(best.minutes) : undefined,
  };
}

function sensorCountLabel(metadata: Record<string, unknown>) {
  const counts = metadata.returned_by_sensor;
  if (!counts || typeof counts !== "object") return "";
  const bySensor = counts as Record<string, number>;
  const modis = bySensor.modis ?? 0;
  const viirs = (bySensor.viirs_snpp ?? 0) + (bySensor.viirs_noaa20 ?? 0) + (bySensor.viirs_noaa21 ?? 0);
  return ` (${modis.toLocaleString()} MODIS, ${viirs.toLocaleString()} VIIRS)`;
}

function themeClass(theme: ThemeMode) {
  return `theme-${theme.toLowerCase()}`;
}

function closeZoomLimitForMode(mode: EarthMode) {
  return mode === "Map" ? minimumMapZoomDistance : minimumTerrainZoomDistance;
}

function cameraHeightForLocation(name: keyof typeof locations, mode: EarthMode) {
  const location = locations[name];
  if (name === "Atlantic View") return location.height;
  return mode === "Map" ? location.height : Math.min(location.height, 1250000);
}

function cameraOrientationForLocation(name: keyof typeof locations, mode: EarthMode) {
  if (name === "Atlantic View" || mode === "Map") return nadirOrientation;
  return obliqueOrientation;
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
  controller.minimumZoomDistance = closeZoomLimitForMode(mode);
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

function updateHotspotOcclusion(viewer: Cesium.Viewer) {
  viewer.entities.values.forEach((entity) => {
    if (!entity.position) return;
    const position = entity.position.getValue(viewer.clock.currentTime);
    entity.show = position ? isPositionVisibleFromCamera(position, viewer.camera.positionWC) : false;
  });
  viewer.scene.requestRender();
}

export default function CesiumFireGlobe() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(layerDefaults);
  const [selectedLocation, setSelectedLocation] = useState<keyof typeof locations>("Atlantic View");
  const [metric, setMetric] = useState("Anomaly score");
  const [lighting, setLighting] = useState<LightingMode>("Day");
  const [theme, setTheme] = useState<ThemeMode>("Default");
  const [showImagery, setShowImagery] = useState(true);
  const [earthMode, setEarthMode] = useState<EarthMode>("3D Terrain");
  const [showFirePoints, setShowFirePoints] = useState(true);
  const [useSensorConfirmationColors, setUseSensorConfirmationColors] = useState(true);
  const [showBuildings, setShowBuildings] = useState(true);
  const [tilesStatus, setTilesStatus] = useState<string | null>(null);
  const [selectedHotspot, setSelectedHotspot] = useState<GlobeHotspot | null>(null);
  const [hotspotEvidence, setHotspotEvidence] = useState<HotspotEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [hotspots, setHotspots] = useState<GlobeHotspot[]>([]);
  const [dataStatus, setDataStatus] = useState("Loading live FIRMS MODIS/VIIRS data...");
  const [viewerReady, setViewerReady] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const buildingsRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const photorealisticTilesRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const photorealisticLoadingRef = useRef(false);
  const terrainRef = useRef<Cesium.TerrainProvider | null>(null);
  const ellipsoidTerrainRef = useRef<Cesium.EllipsoidTerrainProvider | null>(null);
  const hotspotsRef = useRef<GlobeHotspot[]>(hotspots);
  const removeCameraOcclusionRef = useRef<Cesium.Event.RemoveCallback | null>(null);
  const visibleHotspots = useMemo(() => hotspots.filter((hotspot) => layers[hotspot.sensor]), [hotspots, layers]);

  useEffect(() => {
    hotspotsRef.current = hotspots;
  }, [hotspots]);

  async function loadLiveHotspots() {
    setDataStatus("Loading live FIRMS MODIS/VIIRS data...");
    try {
      let response = await getCurrentHotspots(DEFAULT_SENSORS, 1, 3000);
      let daysLoaded = 1;
      if (response.hotspots.length === 0) {
        setDataStatus("No FIRMS detections in the last day. Checking the last 5 days...");
        response = await getCurrentHotspots(DEFAULT_SENSORS, 5, 3000);
        daysLoaded = 5;
      }
      const liveRows = markCrossSensorConfirmed(response.hotspots.map(liveHotspotToGlobeHotspot));
      if (liveRows.length === 0) {
        setHotspots([]);
        setSelectedHotspot(null);
        setDataStatus("No live FIRMS detections were returned for the last 5 days.");
        return;
      }
      setHotspots(liveRows);
      setDataStatus(`Live FIRMS data: ${liveRows.length.toLocaleString()} detections from the last ${daysLoaded === 1 ? "day" : "5 days"}${sensorCountLabel(response.metadata)}.`);
    } catch (error) {
      setHotspots([]);
      setSelectedHotspot(null);
      setDataStatus(`Live FIRMS unavailable: ${normalizeApiError(error)}`);
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
        {
          key: googleMapsKey || undefined,
          onlyUsingWithGoogleGeocoder: true,
        },
        {
          show: earthMode === "Photorealistic",
          maximumScreenSpaceError: 4,
          dynamicScreenSpaceError: false,
          skipLevelOfDetail: false,
          enableCollision: true,
          immediatelyLoadDesiredLevelOfDetail: true,
        },
      );

      if (viewer.isDestroyed()) return;

      tileset.show = earthMode === "Photorealistic";
      viewer.scene.primitives.add(tileset);
      photorealisticTilesRef.current = tileset;
      viewer.scene.globe.show = earthMode !== "Photorealistic" ? true : false;
      setTilesStatus(null);
      viewer.scene.requestRender();
    } catch (error) {
      setTilesStatus(error instanceof Error ? error.message : "Photorealistic 3D tiles are unavailable for this key.");
    } finally {
      photorealisticLoadingRef.current = false;
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
        if (cesiumIonToken) {
          Cesium.Ion.defaultAccessToken = cesiumIonToken;
        }

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
          terrainProvider: ellipsoidTerrain,
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
        });

        viewer.selectedEntityChanged.addEventListener((entity) => {
          const hotspot = hotspotsRef.current.find((record) => record.id === entity?.id);
          setSelectedHotspot(hotspot ?? null);
        });

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
        viewer.scene.globe.atmosphereHueShift = 0;
        viewer.scene.globe.atmosphereSaturationShift = -0.45;
        viewer.scene.globe.atmosphereBrightnessShift = -0.08;
        configureCameraController(viewer, earthMode);
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString(daylightBackgrounds.Day);
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.hueShift = 0;
          viewer.scene.skyAtmosphere.saturationShift = -0.55;
          viewer.scene.skyAtmosphere.brightnessShift = -0.15;
        }
        viewer.scene.sun = undefined;
        viewer.scene.moon = undefined;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(locations["Atlantic View"].lon, locations["Atlantic View"].lat, locations["Atlantic View"].height),
          orientation: nadirOrientation,
        });

        const updateVisibleHotspots = () => updateHotspotOcclusion(viewer);
        removeCameraOcclusionRef.current = viewer.camera.changed.addEventListener(updateVisibleHotspots);

        viewerRef.current = viewer;
        setViewerError(null);
        setViewerReady(true);

        if (cesiumIonToken) {
          void Cesium.createWorldTerrainAsync()
            .then((terrainProvider) => {
              if (disposed || viewer.isDestroyed()) return;
              terrainRef.current = terrainProvider;
              if (earthMode !== "Map") {
                viewer.terrainProvider = terrainProvider;
              }
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
  }, []);

  useEffect(() => {
    void loadLiveHotspots();
  }, []);

  useEffect(() => {
    if (!selectedHotspot) {
      setHotspotEvidence(null);
      setEvidenceError(null);
      setEvidenceLoading(false);
      return;
    }
    void loadEvidence(false);
  }, [selectedHotspot]);

  async function loadEvidence(refresh: boolean) {
    if (!selectedHotspot) return;
    setEvidenceLoading(true);
    setEvidenceError(null);
    try {
      const evidence = await getHotspotEvidence(hotspotToEvidencePayload(selectedHotspot, refresh));
      setHotspotEvidence(evidence);
    } catch (error) {
      setEvidenceError(normalizeApiError(error));
    } finally {
      setEvidenceLoading(false);
    }
  }

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString(daylightBackgrounds[lighting]);
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.baseColor = globeBaseColor;
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
    if (buildingsRef.current) {
      buildingsRef.current.show = earthMode === "3D Terrain" && showBuildings;
    }
    if (photorealisticTilesRef.current) {
      photorealisticTilesRef.current.show = earthMode === "Photorealistic";
    }
    viewer.scene.requestRender();
  }, [earthMode, lighting, showBuildings, showImagery, theme, viewerReady]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (earthMode === "Photorealistic") {
      void loadPhotorealisticTiles(viewer);
    }

    const terrainProvider = earthMode === "Map" ? ellipsoidTerrainRef.current : terrainRef.current;
    if (terrainProvider) {
      viewer.terrainProvider = terrainProvider;
    }

    configureCameraController(viewer, earthMode);
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.show = earthMode !== "Photorealistic" || !photorealisticTilesRef.current;

    if (buildingsRef.current) {
      buildingsRef.current.show = earthMode === "3D Terrain" && showBuildings;
    }

    if (photorealisticTilesRef.current) {
      photorealisticTilesRef.current.show = earthMode === "Photorealistic";
    }

    viewer.scene.requestRender();
  }, [earthMode, viewerReady]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    viewer.entities.removeAll();
    if (!showFirePoints) {
      viewer.scene.requestRender();
      return;
    }
    visibleHotspots.forEach((hotspot) => {
      const anomalyHeight = Math.max(25000, hotspot.anomaly_score * 65000);
      viewer.entities.add({
        id: hotspot.id,
        name: "Active Fire Detection",
        position: Cesium.Cartesian3.fromDegrees(hotspot.longitude, hotspot.latitude, 0),
        point: {
          pixelSize: hotspot.sensor === "VIIRS" ? 11 : 14,
          color: colorForHotspot(hotspot, layers, useSensorConfirmationColors),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.9),
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: 0,
        },
        cylinder: layers["Harmonized Activity"]
          ? {
              length: metric === "FRP" ? (hotspot.frp ?? 1) * 2200 : anomalyHeight,
              topRadius: 18000,
              bottomRadius: 18000,
              material: colorForHotspot(hotspot, layers, useSensorConfirmationColors).withAlpha(0.42),
              outline: true,
              outlineColor: Cesium.Color.WHITE.withAlpha(0.25),
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            }
          : undefined,
      });
    });
    updateHotspotOcclusion(viewer);
    viewer.scene.requestRender();
  }, [layers, metric, showFirePoints, useSensorConfirmationColors, viewerReady, visibleHotspots]);

  function flyToLocation(name: keyof typeof locations) {
    setSelectedLocation(name);
    const destination = locations[name];
    if (!viewerRef.current) return;
    viewerRef.current.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(destination.lon, destination.lat, cameraHeightForLocation(name, earthMode)),
      orientation: cameraOrientationForLocation(name, earthMode),
      duration: 1.2,
    });
  }

  function toggleLayer(layer: LayerKey) {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }));
  }

  function zoom(direction: "in" | "out") {
    const camera = viewerRef.current?.camera;
    if (!camera) return;
    const amount = Math.max(camera.positionCartographic.height * 0.45, 60000);
    if (direction === "in") {
      camera.zoomIn(amount);
    } else {
      camera.zoomOut(amount);
    }
    viewerRef.current?.scene.requestRender();
  }

  return (
    <section className={`cesium-shell command-globe ${themeClass(theme)}`}>
      <div ref={containerRef} className="cesium-container" />
      <aside className="scene-panel">
        <p className="panel-title">Scenes</p>
        <div className="scene-list">
          {sceneItems.map((item, index) => (
            <button key={item.title} className={index === 0 ? "scene-item active" : "scene-item"} type="button">
              <span className="scene-icon">{["O", "+", "=", "~", ">"][index]}</span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </span>
            </button>
          ))}
        </div>
        <div className="scene-note">
          <span>O</span>
          <p>
            <code>Cesium</code> provides the 3D terrain, buildings, and globe. MODIS/VIIRS remain the source of fire detections.
          </p>
        </div>
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
              <button key={mode} className={earthMode === mode ? "active" : ""} type="button" onClick={() => setEarthMode(mode)}>
                {mode}
              </button>
            ))}
          </div>
          <label className="switch-row">
            <span>Imagery</span>
            <input type="checkbox" checked={showImagery} onChange={(event) => setShowImagery(event.target.checked)} />
          </label>
          <label className="switch-row">
            <span>OSM Buildings</span>
            <input
              type="checkbox"
              checked={earthMode === "3D Terrain" && showBuildings}
              disabled={earthMode !== "3D Terrain"}
              onChange={(event) => setShowBuildings(event.target.checked)}
            />
          </label>
          <label className="switch-row">
            <span>Terrain</span>
            <input type="checkbox" checked={earthMode !== "Map"} readOnly />
          </label>
          {tilesStatus && <p className="tiles-status">{tilesStatus}</p>}
          <label className="switch-row">
            <span>Fire Points</span>
            <input type="checkbox" checked={showFirePoints} onChange={(event) => setShowFirePoints(event.target.checked)} />
          </label>
          <label className="switch-row">
            <span>Sensor Colors</span>
            <input type="checkbox" checked={useSensorConfirmationColors} onChange={(event) => setUseSensorConfirmationColors(event.target.checked)} />
          </label>
          {useSensorConfirmationColors && <p className="tiles-status">Green MODIS, yellow VIIRS, red merged confirmation.</p>}
          <button className="option-card refresh-live-data" type="button" onClick={loadLiveHotspots}>
            Refresh FIRMS
          </button>
          <p className="tiles-status">{dataStatus}</p>
        </section>
        <section>
          <p className="panel-title">Fire Layers</p>
          <div className="compact-layer-grid">
            {(Object.keys(layerDefaults) as LayerKey[]).map((layer) => (
              <button key={layer} className={layers[layer] ? "active" : ""} type="button" onClick={() => toggleLayer(layer)}>
                {layer}
              </button>
            ))}
          </div>
          <label className="select-row">
            <span>Location</span>
            <select value={selectedLocation} onChange={(event) => flyToLocation(event.target.value as keyof typeof locations)}>
              {Object.keys(locations).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label className="select-row">
            <span>Column Metric</span>
            <select value={metric} onChange={(event) => setMetric(event.target.value)}>
              <option>Anomaly score</option>
              <option>FRP</option>
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
      <div className="zoom-controls" aria-label="Map zoom controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoom("in")}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoom("out")}>-</button>
      </div>
      {selectedHotspot && (
        <aside className="hotspot-popup">
          <div className="hotspot-popup-title">
            <div>
              <p className="eyebrow">Active Fire Detection</p>
              <h3>{selectedHotspot.sensor} hotspot</h3>
            </div>
            <button type="button" aria-label="Close hotspot details" onClick={() => setSelectedHotspot(null)}>
              X
            </button>
          </div>
          <table className="cesium-info-table">
            <tbody>
              <tr><th>Sensor</th><td>{selectedHotspot.sensor}</td></tr>
              <tr><th>Satellite</th><td>{selectedHotspot.satellite}</td></tr>
              <tr><th>Date</th><td>{selectedHotspot.acq_date}</td></tr>
              <tr><th>Time</th><td>{formatTime(selectedHotspot.acq_time)}</td></tr>
              <tr><th>Latitude</th><td>{selectedHotspot.latitude.toFixed(4)}</td></tr>
              <tr><th>Longitude</th><td>{selectedHotspot.longitude.toFixed(4)}</td></tr>
              <tr><th>FRP</th><td>{selectedHotspot.frp === null ? "Not provided" : `${selectedHotspot.frp} MW`}</td></tr>
              <tr><th>Confidence</th><td>{selectedHotspot.confidence}</td></tr>
              <tr><th>Day/Night</th><td>{selectedHotspot.day_night === "D" ? "Day" : "Night"}</td></tr>
              <tr>
                <th>Merge Status</th>
                <td>
                  {selectedHotspot.cross_sensor_confirmed
                    ? `MODIS + VIIRS nearby (${selectedHotspot.merge_distance_km} km, ${selectedHotspot.merge_time_minutes} min)`
                    : `${selectedHotspot.sensor} only`}
                </td>
              </tr>
              <tr><th>Grid Cell</th><td>{selectedHotspot.grid_id}</td></tr>
              <tr><th>Anomaly</th><td>{selectedHotspot.anomaly_score.toFixed(1)} ({statusForZ(selectedHotspot.anomaly_score)})</td></tr>
            </tbody>
          </table>
          <div className="fire-validation-panel">
            <div className="validation-header">
              <div>
                <p className="eyebrow">Fire Validation</p>
                <h4>{hotspotEvidence?.fusion.final_status ?? "Checking evidence..."}</h4>
              </div>
              <button type="button" onClick={() => loadEvidence(true)} disabled={evidenceLoading}>
                {evidenceLoading ? "..." : "Refresh Evidence"}
              </button>
            </div>
            {hotspotEvidence && (
              <div className="evidence-score">
                <span>System Evidence Score</span>
                <strong>{hotspotEvidence.fusion.system_evidence_score} / 100</strong>
              </div>
            )}
            {evidenceError && <p className="evidence-error">{evidenceError}</p>}
            <div className="validation-stages">
              {(hotspotEvidence?.stages ?? [
                { name: "Satellite Validation", status: "checking" },
                { name: "Regional Source Validation", status: "waiting" },
                { name: "Government Check", status: "waiting" },
                { name: "News Validation", status: "waiting" },
                { name: "NLP Analysis", status: "waiting" },
                { name: "Final Evidence Score", status: "waiting" },
              ]).map((stage) => (
                <div key={stage.name}>
                  <span>{stage.status === "completed" ? "OK" : stage.status === "checking" ? "..." : "O"}</span>
                  <p>{stage.name}</p>
                  {stage.detail && <small>{stage.detail}</small>}
                </div>
              ))}
            </div>
            {hotspotEvidence && (
              <>
                <section>
                  <h4>Location</h4>
                  <p>{String(hotspotEvidence.place.locality ?? hotspotEvidence.place.country ?? "Unknown location")}</p>
                  <small>{String(hotspotEvidence.place.admin_level_1 ?? "")} {String(hotspotEvidence.place.country ?? "")}</small>
                </section>
                <section>
                  <h4>Evidence</h4>
                  <ul>
                    {hotspotEvidence.fusion.why.map((reason) => <li key={reason}>{reason}</li>)}
                    {hotspotEvidence.fusion.uncertainty.map((item) => <li key={item} className="uncertain">{item}</li>)}
                  </ul>
                </section>
                <section>
                  <h4>Local News</h4>
                  {hotspotEvidence.news_evidence.articles.length === 0 ? (
                    <p>No matching local/national report returned yet.</p>
                  ) : hotspotEvidence.news_evidence.articles.slice(0, 3).map((article) => (
                    <article key={`${article.headline}-${article.url}`} className="news-evidence-card">
                      <strong>{article.headline}</strong>
                      <span>{article.publication} - {article.country}</span>
                      <dl>
                        <div><dt>Event</dt><dd>{article.event_type}</dd></div>
                        <div><dt>Relevance</dt><dd>{article.relevance_score}/100</dd></div>
                        <div><dt>Location</dt><dd>{article.location_score}/100</dd></div>
                        <div><dt>Time</dt><dd>{article.time_score}/100</dd></div>
                      </dl>
                      <p>{article.summary}</p>
                      {article.url && <a href={article.url} target="_blank" rel="noreferrer">Open original source</a>}
                    </article>
                  ))}
                </section>
                <section>
                  <h4>AI Analysis</h4>
                  <p>{hotspotEvidence.fusion.ai_analysis}</p>
                </section>
                <section>
                  <h4>Source Transparency</h4>
                  <p>{hotspotEvidence.source_transparency.generated_summary_notice}</p>
                  <small>Satellite: {hotspotEvidence.source_transparency.satellite_sources.slice(0, 4).join(", ")}</small>
                  <small>Government: {hotspotEvidence.source_transparency.government_sources.slice(0, 3).join(", ") || "Not yet available"}</small>
                </section>
              </>
            )}
          </div>
          <p>Live NASA FIRMS MODIS/VIIRS record. Cesium imagery and terrain are visual basemap content only.</p>
        </aside>
      )}
    </section>
  );
}
