import { useEffect, useRef, useState } from "react";
import * as Cesium from "cesium";
import type { HotspotRecord } from "../types/api";

type HomeFireGlobeProps = { hotspots: HotspotRecord[] };

const HOTSPOT_PREFIX = "home-hotspot:";
const ORBIT_PREFIX = "home-orbit:";

function fireColor(frp: number | null) {
  if ((frp ?? 0) >= 100) return Cesium.Color.fromCssColorString("#ff3d1f");
  if ((frp ?? 0) >= 30) return Cesium.Color.fromCssColorString("#ff6b35");
  return Cesium.Color.fromCssColorString("#ffb14a");
}

function orbitPositions(tilt: number, height: number) {
  const positions: Cesium.Cartesian3[] = [];
  for (let lon = -180; lon <= 180; lon += 3) {
    positions.push(Cesium.Cartesian3.fromDegrees(lon, Math.sin(Cesium.Math.toRadians(lon)) * tilt, height));
  }
  return positions;
}

function renderHotspots(viewer: Cesium.Viewer, hotspots: HotspotRecord[]) {
  viewer.entities.values
    .filter((entity) => entity.id.startsWith(HOTSPOT_PREFIX))
    .forEach((entity) => viewer.entities.remove(entity));

  hotspots.slice(0, 600).forEach((hotspot, index) => {
    const color = fireColor(hotspot.frp);
    viewer.entities.add({
      id: `${HOTSPOT_PREFIX}${index}`,
      name: `${hotspot.sensor.toUpperCase()} observation`,
      position: Cesium.Cartesian3.fromDegrees(hotspot.lon, hotspot.lat, 12_000),
      point: {
        pixelSize: Math.min(13, 5 + Math.sqrt(Math.max(0, hotspot.frp ?? 0)) * 0.35),
        color: color.withAlpha(0.96),
        outlineColor: color.withAlpha(0.34),
        outlineWidth: 7,
        disableDepthTestDistance: 0,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 20_000_000),
      },
    });
  });
  viewer.scene.requestRender();
}

export default function HomeFireGlobe({ hotspots }: HomeFireGlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const hotspotsRef = useRef(hotspots);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HotspotRecord | null>(null);
  hotspotsRef.current = hotspots;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || viewerRef.current) return;
    const mount = container;
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let clickHandler: Cesium.ScreenSpaceEventHandler | null = null;

    async function initialize() {
      try {
        for (let attempt = 0; attempt < 90; attempt += 1) {
          if (disposed) return;
          const bounds = mount.getBoundingClientRect();
          if (bounds.width > 0 && bounds.height > 0) break;
          await new Promise((resolve) => requestAnimationFrame(resolve));
        }

        const token = import.meta.env.VITE_CESIUM_ION_TOKEN?.trim();
        if (token) Cesium.Ion.defaultAccessToken = token;
        const localImagery = () =>
          Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"));
        let imagery: Cesium.ImageryProvider;
        if (token) {
          try {
            imagery = await Cesium.createWorldImageryAsync({ style: Cesium.IonWorldImageryStyle.AERIAL });
          } catch {
            imagery = await localImagery();
          }
        } else {
          imagery = await localImagery();
        }
        if (disposed) return;

        const viewer = new Cesium.Viewer(mount, {
          animation: false,
          baseLayer: new Cesium.ImageryLayer(imagery),
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
        });
        viewerRef.current = viewer;
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#082447");
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.globe.depthTestAgainstTerrain = false;
        viewer.scene.backgroundColor = Cesium.Color.TRANSPARENT;
        viewer.scene.sun = undefined;
        viewer.scene.moon = undefined;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 1_400_000;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 20_000_000;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(80, 24, 13_000_000),
          orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
        });

        [
          { id: "a", tilt: 24, height: 220_000 },
          { id: "b", tilt: -38, height: 300_000 },
        ].forEach((orbit) => {
          viewer.entities.add({
            id: `${ORBIT_PREFIX}${orbit.id}`,
            polyline: {
              positions: orbitPositions(orbit.tilt, orbit.height),
              width: 1,
              material: new Cesium.PolylineGlowMaterialProperty({
                color: Cesium.Color.fromCssColorString("#67d9ff").withAlpha(0.2),
                glowPower: 0.15,
              }),
            },
          });
        });

        resizeObserver = new ResizeObserver(() => {
          if (!viewer.isDestroyed()) {
            viewer.resize();
            viewer.scene.requestRender();
          }
        });
        resizeObserver.observe(mount);
        renderHotspots(viewer, hotspotsRef.current);
        clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        clickHandler.setInputAction((movement: { position: Cesium.Cartesian2 }) => {
          const picked = viewer.scene.pick(movement.position) as { id?: Cesium.Entity } | undefined;
          const id = picked?.id?.id;
          if (typeof id !== "string" || !id.startsWith(HOTSPOT_PREFIX)) {
            setSelected(null);
            return;
          }
          const index = Number(id.slice(HOTSPOT_PREFIX.length));
          setSelected(hotspotsRef.current[index] ?? null);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
        setError(null);
        viewer.scene.requestRender();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Earth visualization unavailable");
      }
    }

    void initialize();
    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      clickHandler?.destroy();
      const viewer = viewerRef.current;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    renderHotspots(viewer, hotspots);
  }, [hotspots]);

  return (
    <div className="home-globe-stage" aria-label="Interactive globe showing current satellite fire observations">
      <div ref={containerRef} className="home-globe-canvas" />
      <div className="home-globe-vignette" aria-hidden="true" />
      <div className="home-globe-mode"><span /> Interactive Earth</div>
      {selected && (
        <aside className="home-hotspot-popover" aria-live="polite">
          <button type="button" onClick={() => setSelected(null)} aria-label="Close observation details">×</button>
          <p>Satellite observation</p>
          <strong>{selected.satellite || selected.sensor.replace(/_/g, " ").toUpperCase()}</strong>
          <dl>
            <div><dt>Coordinates</dt><dd>{selected.lat.toFixed(3)}°, {selected.lon.toFixed(3)}°</dd></div>
            <div><dt>Observed</dt><dd>{new Date(selected.acq_datetime).toLocaleString()}</dd></div>
            <div><dt>Confidence</dt><dd>{Math.round(selected.confidence_pct)}%</dd></div>
            <div><dt>Fire power</dt><dd>{selected.frp == null ? "Not reported" : `${selected.frp.toFixed(1)} MW`}</dd></div>
          </dl>
          <small>A hotspot is a satellite observation, not automatic wildfire confirmation.</small>
        </aside>
      )}
      {error && <p className="home-globe-error">Earth feed unavailable: {error}</p>}
    </div>
  );
}
