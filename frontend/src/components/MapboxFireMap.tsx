import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl, { type GeoJSONSource, type Map } from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { sampleHotspots, type FireSensor, type SampleHotspot } from "../data/sampleHotspots";

type LayerKey = FireSensor | "Harmonized Activity" | "Anomaly Layer";

const locations = {
  Bangladesh: { lat: 23.685, lon: 90.3563, zoom: 7.2 },
  Amazon: { lat: -3.4653, lon: -62.2159, zoom: 6.4 },
  "California, USA": { lat: 38.5816, lon: -121.4944, zoom: 7 },
  "Northern Australia": { lat: -12.4634, lon: 130.8456, zoom: 6.8 },
  Greece: { lat: 38.05, lon: 23.78, zoom: 7.5 },
};

const layerDefaults: Record<LayerKey, boolean> = {
  MODIS: true,
  VIIRS: true,
  "Harmonized Activity": true,
  "Anomaly Layer": true,
};

function statusForZ(z: number) {
  if (z >= 3) return "Very unusual";
  if (z >= 2) return "Unusual";
  if (z >= 1) return "Elevated";
  return "Normal";
}

function formatTime(value: string) {
  return `${value.slice(0, 2)}:${value.slice(2)}`;
}

function toFeatureCollection(hotspots: SampleHotspot[]) {
  return {
    type: "FeatureCollection" as const,
    features: hotspots.map((hotspot) => ({
      type: "Feature" as const,
      id: hotspot.id,
      geometry: {
        type: "Point" as const,
        coordinates: [hotspot.longitude, hotspot.latitude],
      },
      properties: hotspot,
    })),
  };
}

function toColumnFeatureCollection(hotspots: SampleHotspot[]) {
  return {
    type: "FeatureCollection" as const,
    features: hotspots.map((hotspot) => {
      const size = 0.06;
      const west = hotspot.longitude - size;
      const east = hotspot.longitude + size;
      const south = hotspot.latitude - size;
      const north = hotspot.latitude + size;
      return {
        type: "Feature" as const,
        id: `${hotspot.id}-column`,
        geometry: {
          type: "Polygon" as const,
          coordinates: [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
          ]],
        },
        properties: hotspot,
      };
    }),
  };
}

export default function MapboxFireMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(layerDefaults);
  const [selectedLocation, setSelectedLocation] = useState<keyof typeof locations>("Bangladesh");
  const [metric, setMetric] = useState("Anomaly score");
  const [mapError, setMapError] = useState<string | null>(null);
  const mapboxToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined;

  const visibleHotspots = useMemo(() => sampleHotspots.filter((hotspot) => layers[hotspot.sensor]), [layers]);
  const fireData = useMemo(() => toFeatureCollection(visibleHotspots), [visibleHotspots]);
  const columnData = useMemo(() => toColumnFeatureCollection(visibleHotspots), [visibleHotspots]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !mapboxToken) return;

    mapboxgl.accessToken = mapboxToken;
    const center = locations.Bangladesh;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/satellite-streets-v12",
      center: [center.lon, center.lat],
      zoom: center.zoom,
      pitch: 64,
      bearing: -22,
      antialias: true,
    });

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "bottom-left");

    map.on("error", (event) => {
      const message = event.error?.message || "Mapbox failed to load the map.";
      setMapError(message);
    });

    map.on("load", () => {
      map.setFog({
        color: "rgb(186, 210, 235)",
        "high-color": "rgb(36, 92, 223)",
        "horizon-blend": 0.08,
        "space-color": "rgb(7, 17, 31)",
        "star-intensity": 0.08,
      });

      map.addSource("mapbox-dem", {
        type: "raster-dem",
        url: "mapbox://mapbox.mapbox-terrain-dem-v1",
        tileSize: 512,
        maxzoom: 14,
      });
      map.setTerrain({ source: "mapbox-dem", exaggeration: 1.45 });

      const firstSymbolLayer = map.getStyle().layers?.find((layer) => layer.type === "symbol")?.id;
      if (map.getSource("composite")) {
        map.addLayer(
          {
            id: "3d-buildings",
            source: "composite",
            "source-layer": "building",
            filter: ["==", "extrude", "true"],
            type: "fill-extrusion",
            minzoom: 14,
            paint: {
              "fill-extrusion-color": "#9fb4c7",
              "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15.05, ["get", "height"]],
              "fill-extrusion-base": ["interpolate", ["linear"], ["zoom"], 14, 0, 15.05, ["get", "min_height"]],
              "fill-extrusion-opacity": 0.62,
            },
          },
          firstSymbolLayer,
        );
      }

      map.addSource("fire-hotspots", {
        type: "geojson",
        data: fireData,
      });
      map.addSource("fire-columns", {
        type: "geojson",
        data: columnData,
      });

      map.addLayer({
        id: "fire-heat",
        type: "heatmap",
        source: "fire-hotspots",
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "anomaly_score"], 0, 0.2, 3, 1],
          "heatmap-intensity": 0.75,
          "heatmap-radius": 42,
          "heatmap-opacity": ["case", layers["Harmonized Activity"], 0.55, 0],
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(56, 189, 248, 0)",
            0.35,
            "rgba(250, 204, 21, 0.75)",
            0.7,
            "rgba(249, 115, 22, 0.85)",
            1,
            "rgba(239, 68, 68, 0.95)",
          ],
        },
      });

      map.addLayer({
        id: "fire-activity-columns",
        type: "fill-extrusion",
        source: "fire-columns",
        paint: {
          "fill-extrusion-color": [
            "case",
            [">=", ["get", "anomaly_score"], 3],
            "#d946ef",
            [">=", ["get", "anomaly_score"], 2],
            "#ef4444",
            ["==", ["get", "sensor"], "VIIRS"],
            "#38bdf8",
            "#f59e0b",
          ],
          "fill-extrusion-height": ["interpolate", ["linear"], ["get", metric === "FRP" ? "frp" : "anomaly_score"], 0, 1200, 65, 52000],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": ["case", layers["Harmonized Activity"], 0.74, 0],
        },
      });

      map.addLayer({
        id: "fire-points",
        type: "circle",
        source: "fire-hotspots",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", metric === "FRP" ? "frp" : "anomaly_score"], 0, 6, 65, 18],
          "circle-color": [
            "case",
            [">=", ["get", "anomaly_score"], 3],
            "#d946ef",
            [">=", ["get", "anomaly_score"], 2],
            "#ef4444",
            ["==", ["get", "sensor"], "VIIRS"],
            "#38bdf8",
            "#f59e0b",
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": ["case", layers["Anomaly Layer"], 0.95, 0.78],
        },
      });

      map.on("click", "fire-points", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties as unknown as SampleHotspot;
        const coordinates = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        popupRef.current?.remove();
        popupRef.current = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, maxWidth: "340px" })
          .setLngLat(coordinates)
          .setHTML(`
            <strong>Active Fire Detection</strong>
            <table class="mapbox-popup-table">
              <tr><th>Sensor</th><td>${props.sensor}</td></tr>
              <tr><th>Satellite</th><td>${props.satellite}</td></tr>
              <tr><th>Date</th><td>${props.acq_date}</td></tr>
              <tr><th>Time</th><td>${formatTime(props.acq_time)}</td></tr>
              <tr><th>Latitude</th><td>${props.latitude.toFixed(4)}</td></tr>
              <tr><th>Longitude</th><td>${props.longitude.toFixed(4)}</td></tr>
              <tr><th>FRP</th><td>${props.frp === null ? "Not provided" : `${props.frp} MW`}</td></tr>
              <tr><th>Confidence</th><td>${props.confidence}</td></tr>
              <tr><th>Anomaly</th><td>${props.anomaly_score.toFixed(1)} (${statusForZ(props.anomaly_score)})</td></tr>
            </table>
          `)
          .addTo(map);
      });

      map.on("mouseenter", "fire-points", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "fire-points", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [columnData, fireData, layers, mapboxToken, metric]);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource("fire-hotspots") as GeoJSONSource | undefined;
    const columnSource = map?.getSource("fire-columns") as GeoJSONSource | undefined;
    source?.setData(fireData);
    columnSource?.setData(columnData);
    if (map?.getLayer("fire-heat")) {
      map.setPaintProperty("fire-heat", "heatmap-opacity", layers["Harmonized Activity"] ? 0.55 : 0);
    }
  }, [columnData, fireData, layers]);

  function flyToLocation(name: keyof typeof locations) {
    setSelectedLocation(name);
    const destination = locations[name];
    mapRef.current?.flyTo({
      center: [destination.lon, destination.lat],
      zoom: destination.zoom,
      pitch: 64,
      bearing: -22,
      duration: 1000,
    });
  }

  function toggleLayer(layer: LayerKey) {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }));
  }

  return (
    <section className="cesium-shell">
      <div className="cesium-toolbar">
        <div>
          <p className="eyebrow">Mapbox Fire Map</p>
          <h2>MODIS and VIIRS Hotspot Map</h2>
        </div>
        <div className="toolbar-controls">
          <label>
            Fly to
            <select value={selectedLocation} onChange={(event) => flyToLocation(event.target.value as keyof typeof locations)}>
              {Object.keys(locations).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            Symbol metric
            <select value={metric} onChange={(event) => setMetric(event.target.value)}>
              <option>Anomaly score</option>
              <option>FRP</option>
            </select>
          </label>
        </div>
      </div>
      <div className="layer-bar">
        {(Object.keys(layerDefaults) as LayerKey[]).map((layer) => (
          <button key={layer} className={layers[layer] ? "active-tool" : ""} type="button" onClick={() => toggleLayer(layer)}>
            {layer}
          </button>
        ))}
      </div>
      <div ref={containerRef} className="cesium-container mapbox-container" />
      {!mapboxToken && (
        <div className="cesium-error-panel">
          <h3>Mapbox token needed</h3>
          <p>Add VITE_MAPBOX_ACCESS_TOKEN to frontend/.env.local, then restart Vite.</p>
        </div>
      )}
      {mapError && (
        <div className="cesium-error-panel">
          <h3>Mapbox could not load</h3>
          <p>{mapError}</p>
        </div>
      )}
    </section>
  );
}
