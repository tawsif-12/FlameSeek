import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { EVENT, GLOBE_HOTSPOTS } from "./data";

type Props = { interactive?: boolean; spin?: boolean; stars?: boolean; altitude?: number; lon?: number; tooltip?: ReactNode };

// Offline globe: bundled Natural Earth imagery plus scripted hotspots. No tokens, no network calls.
export default function DemoGlobe({ interactive = true, spin = false, stars = true, altitude = 13_500_000, lon = 86, tooltip }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let viewer: Cesium.Viewer | undefined;
    let cancelled = false;
    (async () => {
      const provider = await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"));
      if (cancelled || !hostRef.current) return;
      viewer = new Cesium.Viewer(hostRef.current, {
        baseLayer: new Cesium.ImageryLayer(provider),
        baseLayerPicker: false, fullscreenButton: false, geocoder: false, homeButton: false, infoBox: false, sceneModePicker: false,
        selectionIndicator: false, timeline: false, animation: false, navigationHelpButton: false,
      });
      const { scene } = viewer;
      scene.backgroundColor = Cesium.Color.fromCssColorString("#070b14");
      if (scene.skyBox) scene.skyBox.show = stars;
      if (scene.sun) scene.sun.show = false;
      if (scene.moon) scene.moon.show = false;
      scene.globe.enableLighting = false;
      scene.globe.depthTestAgainstTerrain = true;
      scene.globe.baseColor = Cesium.Color.fromCssColorString("#0b2447");
      const layer = viewer.imageryLayers.get(0);
      layer.brightness = 0.62;
      layer.contrast = 1.3;
      layer.saturation = 1.25;
      layer.gamma = 0.9;

      const points = scene.primitives.add(new Cesium.PointPrimitiveCollection());
      for (const h of GLOBE_HOTSPOTS) {
        const css = h.level > 0.82 ? "#ff5a3c" : h.level > 0.4 ? "#ff8a3d" : "#ffc24d";
        points.add({ position: Cesium.Cartesian3.fromDegrees(h.lon, h.lat, 12_000), pixelSize: h.level > 0.82 ? 3.6 : 2.8, color: Cesium.Color.fromCssColorString(css).withAlpha(0.92) });
      }

      scene.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(lon, 17, altitude) });
      const ctl = scene.screenSpaceCameraController;
      ctl.enableTilt = false;
      ctl.minimumZoomDistance = 3_000_000;
      ctl.maximumZoomDistance = 30_000_000;
      if (!interactive) ctl.enableInputs = false;
      if (spin) viewer.clock.onTick.addEventListener(() => scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, -0.00025));

      const eventPos = Cesium.Cartesian3.fromDegrees(EVENT.lon, EVENT.lat, 12_000);
      scene.postRender.addEventListener(() => {
        const tip = tipRef.current;
        if (!tip) return;
        // horizon test: the point is on the near side when its angle from the camera axis is inside the visible cap
        const cam = scene.camera.positionWC;
        const cos = Cesium.Cartesian3.dot(cam, eventPos) / (Cesium.Cartesian3.magnitude(cam) * Cesium.Cartesian3.magnitude(eventPos));
        const visible = cos > 6_378_137 / Cesium.Cartesian3.magnitude(cam);
        const win = Cesium.SceneTransforms.worldToWindowCoordinates(scene, eventPos);
        tip.style.display = visible && win ? "block" : "none";
        if (win) {
          tip.style.left = `${win.x}px`;
          tip.style.top = `${win.y}px`;
        }
      });
    })();
    return () => {
      cancelled = true;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
  }, [interactive, spin, stars, altitude, lon]);

  return (
    <div className="globe" style={{ position: "absolute", inset: 0 }}>
      <div ref={hostRef} style={{ position: "absolute", inset: 0 }} />
      {tooltip && <div ref={tipRef} className="tip" style={{ display: "none" }}>{tooltip}</div>}
    </div>
  );
}
