import { useEffect, useMemo, useRef, useState } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { sampleHotspots } from "../data/sampleHotspots";

type FeatureKey = "live" | "history" | "calendar" | "aqi" | "anomalies";

type Feature = {
  key: FeatureKey;
  title: string;
  kicker: string;
  body: string;
  lat: number;
  lon: number;
  height: number;
};

type FireLayer = "MODIS" | "VIIRS" | "Harmonized Activity" | "Air Quality";

const features: Feature[] = [
  {
    key: "live",
    title: "LIVE FIRES",
    kicker: "Current MODIS & VIIRS detections",
    body: "Near-real-time active-fire observations remain separated by sensor while the harmonized layer highlights comparable activity intensity.",
    lat: 2,
    lon: 18,
    height: 12000000,
  },
  {
    key: "history",
    title: "HISTORICAL PATTERNS",
    kicker: "Explore more than two decades of burning activity",
    body: "Long-running NASA records reveal seasonal burning regimes, land-use cycles, and persistent regional fire corridors.",
    lat: -3.5,
    lon: -62.2,
    height: 2600000,
  },
  {
    key: "calendar",
    title: "BURNING CALENDAR",
    kicker: "Discover recurring critical fire periods",
    body: "Sensor-aware calendars expose when activity typically intensifies and which windows deserve closer monitoring.",
    lat: 23.7,
    lon: 90.3,
    height: 2200000,
  },
  {
    key: "aqi",
    title: "AIR QUALITY",
    kicker: "Explore current AQI and PM2.5 context",
    body: "Optional air-quality context helps connect observed fire activity with smoke exposure and atmospheric conditions.",
    lat: 38.5,
    lon: -121.5,
    height: 2600000,
  },
  {
    key: "anomalies",
    title: "ANOMALIES",
    kicker: "Identify unusually high burning activity",
    body: "Anomaly scoring compares current observations with historical baselines instead of treating raw hotspot totals as equivalent.",
    lat: -12.4,
    lon: 130.8,
    height: 2300000,
  },
];

const legendItems: Array<[FireLayer, string]> = [
  ["MODIS", "#ffd166"],
  ["VIIRS", "#4dd6ff"],
  ["Harmonized Activity", "#ff8a3d"],
  ["Air Quality", "#9be86f"],
];

function formatHotspotTime(value: string) {
  return `${value.slice(0, 2)}:${value.slice(2)}`;
}

function FireHarmonyGlobe({
  activeFeature,
  exploreSignal,
}: {
  activeFeature: Feature;
  exploreSignal: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const [layers, setLayers] = useState<Record<FireLayer, boolean>>({
    MODIS: true,
    VIIRS: true,
    "Harmonized Activity": true,
    "Air Quality": false,
  });
  const [selectedHotspot, setSelectedHotspot] = useState<(typeof sampleHotspots)[number] | null>(null);

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;
    let disposed = false;
    let removeTick: Cesium.Event.RemoveCallback | undefined;

    async function init() {
      try {
        const token = import.meta.env.VITE_CESIUM_ION_TOKEN;
        if (token) Cesium.Ion.defaultAccessToken = token;

        const imagery = token
          ? await Cesium.createWorldImageryAsync({ style: Cesium.IonWorldImageryStyle.AERIAL })
          : await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"));

        if (!containerRef.current || disposed) return;

        const viewer = new Cesium.Viewer(containerRef.current, {
          animation: false,
          baseLayer: new Cesium.ImageryLayer(imagery),
          baseLayerPicker: false,
          contextOptions: {
            webgl: {
              alpha: true,
              antialias: true,
            },
          },
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          requestRenderMode: false,
        });

        viewer.scene.backgroundColor = Cesium.Color.TRANSPARENT;
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#06172d");
        viewer.scene.globe.maximumScreenSpaceError = 1.3;
        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.globe.atmosphereLightIntensity = 8;
        viewer.scene.globe.atmosphereSaturationShift = -0.15;
        viewer.scene.globe.atmosphereBrightnessShift = 0.18;
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.saturationShift = -0.2;
          viewer.scene.skyAtmosphere.brightnessShift = 0.28;
        }
        if (viewer.scene.skyBox) viewer.scene.skyBox.show = false;
        if (viewer.scene.sun) viewer.scene.sun.show = false;
        if (viewer.scene.moon) viewer.scene.moon.show = false;
        viewer.scene.screenSpaceCameraController.enableInputs = true;
        viewer.scene.screenSpaceCameraController.enableTilt = true;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 700000;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 19000000;
        viewer.scene.screenSpaceCameraController.inertiaSpin = 0.92;
        viewer.scene.screenSpaceCameraController.inertiaZoom = 0.84;
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(18, 2, 12000000),
          orientation: {
            heading: Cesium.Math.toRadians(14),
            pitch: Cesium.Math.toRadians(-82),
            roll: 0,
          },
        });

        sampleHotspots.forEach((hotspot) => {
          const color = hotspot.sensor === "VIIRS" ? Cesium.Color.fromCssColorString("#4dd6ff") : Cesium.Color.fromCssColorString("#ffd166");
          viewer.entities.add({
            id: `home-${hotspot.id}`,
            properties: {
              hotspotId: hotspot.id,
              sensor: hotspot.sensor,
            },
            position: Cesium.Cartesian3.fromDegrees(hotspot.longitude, hotspot.latitude),
            point: {
              pixelSize: new Cesium.CallbackProperty(() => {
                const pulse = Math.sin(Date.now() / 620) * 0.55;
                return (hotspot.sensor === "VIIRS" ? 5.8 : 6.6) + pulse;
              }, false),
              color: color.withAlpha(1),
              outlineColor: color.withAlpha(0.46),
              outlineWidth: 4,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new Cesium.NearFarScalar(1200000, 1, 16000000, 0.65),
            },
            ellipse: {
              semiMajorAxis: 85000 + hotspot.harmonized_activity_index * 28000,
              semiMinorAxis: 85000 + hotspot.harmonized_activity_index * 28000,
              material: Cesium.Color.fromCssColorString("#ff8a3d").withAlpha(0.075),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString("#ff8a3d").withAlpha(0.24),
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            },
          });
        });

        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((movement: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
          const picked = viewer.scene.pick(movement.position);
          const id = picked?.id?.properties?.hotspotId?.getValue();
          setSelectedHotspot(sampleHotspots.find((hotspot) => hotspot.id === id) ?? null);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        removeTick = viewer.clock.onTick.addEventListener(() => {
          if (!viewer.scene.screenSpaceCameraController.enableInputs) return;
          viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, -0.00008);
        });

        viewerRef.current = viewer;
      } catch {
        // The hero keeps its explanatory UI even if Cesium cannot initialize.
      }
    }

    void init();

    return () => {
      disposed = true;
      removeTick?.();
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.entities.values.forEach((entity) => {
      const sensor = entity.properties?.sensor?.getValue() as FireLayer | undefined;
      if (sensor === "MODIS" || sensor === "VIIRS") {
        entity.show = Boolean(layers[sensor]);
        if (entity.ellipse) entity.ellipse.show = new Cesium.ConstantProperty(layers["Harmonized Activity"]);
      }
    });
    viewer.scene.requestRender();
  }, [layers]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(activeFeature.lon, activeFeature.lat, activeFeature.height),
      orientation: {
        heading: Cesium.Math.toRadians(10),
        pitch: Cesium.Math.toRadians(-68),
        roll: 0,
      },
      duration: 1.5,
      easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
    });
  }, [activeFeature]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || exploreSignal === 0) return;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(activeFeature.lon, activeFeature.lat, Math.min(activeFeature.height, 3300000)),
      orientation: {
        heading: Cesium.Math.toRadians(18),
        pitch: Cesium.Math.toRadians(-56),
        roll: 0,
      },
      duration: 1.8,
      easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
    });
  }, [activeFeature, exploreSignal]);

  function toggleLayer(layer: FireLayer) {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }));
  }

  return (
    <div className="fire-earth-stage" aria-label="Interactive 3D Earth with MODIS and VIIRS fire hotspots">
      <div ref={containerRef} className="fire-earth-canvas" />
      <div className="earth-atmosphere" />
      <div className="fire-stats-panel">
        <span>GLOBAL FIRE ACTIVITY</span>
        <strong>12,431</strong>
        <dl>
          <div><dt>MODIS</dt><dd>3,280</dd></div>
          <div><dt>VIIRS</dt><dd>9,151</dd></div>
          <div><dt>Current Activity</dt><dd>Elevated</dd></div>
          <div><dt>Updated</dt><dd>12 min ago</dd></div>
        </dl>
        <small>Demo data</small>
      </div>
      <div className="fire-legend" aria-label="Fire layer legend">
        {legendItems.map(([label, color]) => (
          <button key={label} className={layers[label] ? "active" : ""} type="button" onClick={() => toggleLayer(label)}>
            <i style={{ background: color }} />{label}
          </button>
        ))}
      </div>
      {selectedHotspot && (
        <aside className="hero-hotspot-card">
          <button type="button" aria-label="Close hotspot details" onClick={() => setSelectedHotspot(null)}>X</button>
          <strong>{selectedHotspot.sensor} Active Fire</strong>
          <span>{selectedHotspot.satellite} • {selectedHotspot.acq_date} {formatHotspotTime(selectedHotspot.acq_time)}</span>
          <dl>
            <div><dt>Satellite</dt><dd>{selectedHotspot.satellite}</dd></div>
            <div><dt>Date/Time</dt><dd>{selectedHotspot.acq_date} {formatHotspotTime(selectedHotspot.acq_time)}</dd></div>
            <div><dt>FRP</dt><dd>{selectedHotspot.frp ?? "N/A"} MW</dd></div>
            <div><dt>Confidence</dt><dd>{selectedHotspot.confidence}</dd></div>
            <div><dt>Coordinates</dt><dd>{selectedHotspot.latitude.toFixed(2)}, {selectedHotspot.longitude.toFixed(2)}</dd></div>
            <div><dt>Day/Night</dt><dd>{selectedHotspot.day_night === "D" ? "Day" : "Night"}</dd></div>
          </dl>
        </aside>
      )}
    </div>
  );
}

export default function HomePage() {
  const [activeKey, setActiveKey] = useState<FeatureKey>("live");
  const [exploreSignal, setExploreSignal] = useState(0);
  const activeFeature = useMemo(() => features.find((feature) => feature.key === activeKey) ?? features[0], [activeKey]);

  function exploreEarth() {
    setActiveKey("live");
    setExploreSignal((value) => value + 1);
  }

  return (
    <main className="fire-home">
      <section className="fire-hero" id="earth">
        <div className="starfield" />
        <FireHarmonyGlobe activeFeature={activeFeature} exploreSignal={exploreSignal} />
        <div className="hero-copy" key={activeFeature.key}>
          <p className="mission-label">NASA Space Apps Challenge</p>
          <h1>FIREHARMONY</h1>
          <h2>A Harmonized View of Global Burning Activity</h2>
          <p>
            Explore decades of MODIS and VIIRS active-fire observations, discover historical burning patterns,
            detect unusual activity, and understand critical fire periods across the planet.
          </p>
          <div className="hero-actions">
            <button className="mission-button primary" type="button" onClick={exploreEarth}>EXPLORE EARTH</button>
            <a className="mission-button secondary" href="/fire-map">VIEW LIVE FIRE ACTIVITY</a>
          </div>
          <p className="science-note">3D basemap: Google/Cesium • Fire observations: NASA MODIS & VIIRS</p>
        </div>
        <div className="feature-dock" aria-label="FireHarmony feature selector">
          {features.map((feature) => (
            <button
              key={feature.key}
              className={feature.key === activeKey ? "feature-card active" : "feature-card"}
              type="button"
              onClick={() => setActiveKey(feature.key)}
            >
              <span className={`feature-orb ${feature.key}`} />
              <strong>{feature.title}</strong>
              <small>{feature.kicker}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="analysis-flow" id="explorer">
        <article>
          <span>01</span>
          <h2>3D Global Fire Explorer</h2>
          <p>{activeFeature.body}</p>
        </article>
        <article>
          <span>02</span>
          <h2>Harmonization Explanation</h2>
          <p>MODIS and VIIRS observations are preserved by sensor, then compared through a separate harmonized activity index.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Burning Activity Calendar</h2>
          <p>Calendar views turn detections into recurring critical periods for a selected region and date range.</p>
        </article>
        <article>
          <span>04</span>
          <h2>Historical Analytics</h2>
          <p>Trend and anomaly charts reveal whether current fire activity is typical, elevated, or unusual.</p>
        </article>
        <article>
          <span>05</span>
          <h2>Air Quality Context</h2>
          <p>AQI and PM2.5 layers are contextual overlays, not fire-detection sources.</p>
        </article>
        <article>
          <span>06</span>
          <h2>Anomaly Detection</h2>
          <p>Observed activity is evaluated against historical baselines to surface unusually high burning activity.</p>
        </article>
        <article>
          <span>07</span>
          <h2>NASA Data Sources</h2>
          <p>NASA FIRMS MODIS and VIIRS active-fire products remain the authoritative observation records.</p>
        </article>
      </section>

    </main>
  );
}
