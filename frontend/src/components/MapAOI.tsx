import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet-draw";
import { CircleMarker, FeatureGroup, MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { getCurrentHotspots, normalizeApiError } from "../api/client";
import { useAppContext } from "../context/AppContext";
import type { BBox, HotspotRecord, SensorName } from "../types/api";

const SENSOR_COLORS: Record<SensorName, { stroke: string; fill: string }> = {
  modis: { stroke: "#b91c1c", fill: "#ef4444" },
  viirs_snpp: { stroke: "#c2410c", fill: "#f97316" },
  viirs_noaa20: { stroke: "#a16207", fill: "#eab308" },
  viirs_noaa21: { stroke: "#7c3aed", fill: "#a855f7" },
};

function bboxFromBounds(bounds: L.LatLngBounds): BBox {
  return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
}

function DrawControls() {
  const map = useMap();
  const { setBbox } = useAppContext();

  useEffect(() => {
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    const control = new L.Control.Draw({
      draw: {
        marker: false,
        circle: false,
        circlemarker: false,
        polygon: false,
        polyline: false,
        rectangle: {},
      },
      edit: { featureGroup: drawnItems },
    });
    map.addControl(control);

    const updateBounds = (layer: L.Layer) => {
      if ("getBounds" in layer) {
        const bounds = (layer as L.Rectangle).getBounds();
        setBbox(bboxFromBounds(bounds));
      }
    };

    map.on(L.Draw.Event.CREATED, (event: L.LeafletEvent) => {
      const created = event as L.DrawEvents.Created;
      drawnItems.clearLayers();
      drawnItems.addLayer(created.layer);
      updateBounds(created.layer);
    });
    map.on(L.Draw.Event.EDITED, (event: L.LeafletEvent) => {
      const edited = event as L.DrawEvents.Edited;
      edited.layers.eachLayer(updateBounds);
    });
    map.on(L.Draw.Event.DELETED, () => setBbox(null));

    return () => {
      map.removeControl(control);
      map.removeLayer(drawnItems);
    };
  }, [map, setBbox]);

  return null;
}

function DirectDragSelector({ active, onDone }: { active: boolean; onDone: () => void }) {
  const map = useMap();
  const { setBbox } = useAppContext();
  const startRef = useRef<L.LatLng | null>(null);
  const rectRef = useRef<L.Rectangle | null>(null);

  useEffect(() => {
    if (active) {
      map.dragging.disable();
      map.getContainer().classList.add("selecting-aoi");
    } else {
      map.dragging.enable();
      map.getContainer().classList.remove("selecting-aoi");
    }
    return () => {
      map.dragging.enable();
      map.getContainer().classList.remove("selecting-aoi");
    };
  }, [active, map]);

  useMapEvents({
    mousedown(event) {
      if (!active) return;
      startRef.current = event.latlng;
      rectRef.current?.remove();
      rectRef.current = L.rectangle(L.latLngBounds(event.latlng, event.latlng), {
        color: "#1d4ed8",
        weight: 2,
        fillOpacity: 0.12,
      }).addTo(map);
    },
    mousemove(event) {
      if (!active || !startRef.current || !rectRef.current) return;
      rectRef.current.setBounds(L.latLngBounds(startRef.current, event.latlng));
    },
    mouseup(event) {
      if (!active || !startRef.current || !rectRef.current) return;
      rectRef.current.setBounds(L.latLngBounds(startRef.current, event.latlng));
      setBbox(bboxFromBounds(rectRef.current.getBounds()));
      startRef.current = null;
      onDone();
    },
  });

  return null;
}

export default function MapAOI() {
  const { sensors } = useAppContext();
  const [selecting, setSelecting] = useState(false);
  const [hotspots, setHotspots] = useState<HotspotRecord[]>([]);
  const [status, setStatus] = useState("Loading current hotspots...");

  useEffect(() => {
    if (sensors.length === 0) {
      setHotspots([]);
      setStatus("Select at least one sensor to show hotspots.");
      return;
    }
    let cancelled = false;
    setStatus(`Loading current hotspots for ${sensors.length} sensor${sensors.length === 1 ? "" : "s"}...`);
    getCurrentHotspots(sensors)
      .then((response) => {
        if (cancelled) return;
        setHotspots(response.hotspots);
        const filteredCounts = (response.metadata.filtered_by_sensor ?? {}) as Record<string, number>;
        const returnedCounts = response.hotspots.reduce<Record<string, number>>((acc, hotspot) => {
          acc[hotspot.sensor] = (acc[hotspot.sensor] ?? 0) + 1;
          return acc;
        }, {});
        const countText = sensors
          .map((sensor) => `${sensor}: ${(filteredCounts[sensor] ?? 0).toLocaleString()} total / ${(returnedCounts[sensor] ?? 0).toLocaleString()} shown`)
          .join(" | ");
        setStatus(countText || "No current hotspots for selected sensors.");
      })
      .catch((error) => {
        if (!cancelled) setStatus(normalizeApiError(error));
      });
    return () => {
      cancelled = true;
    };
  }, [sensors]);

  return (
    <section className="map-panel">
      <div className="map-toolbar">
        <button type="button" className={selecting ? "secondary-button active-tool" : "secondary-button"} onClick={() => setSelecting((value) => !value)}>
          {selecting ? "Drag on map..." : "Select AOI"}
        </button>
        <span>{status}</span>
      </div>
      <MapContainer center={[5, 20]} zoom={3} minZoom={2} scrollWheelZoom className="map">
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {hotspots.map((hotspot, index) => (
          <CircleMarker
            key={`${hotspot.sensor}-${hotspot.acq_datetime}-${hotspot.lat}-${hotspot.lon}-${index}`}
            center={[hotspot.lat, hotspot.lon]}
            radius={Math.max(3, Math.min(9, (hotspot.frp ?? 5) / 25))}
            pathOptions={{ color: SENSOR_COLORS[hotspot.sensor].stroke, fillColor: SENSOR_COLORS[hotspot.sensor].fill, fillOpacity: 0.55, weight: 1 }}
          />
        ))}
        <FeatureGroup />
        <DrawControls />
        <DirectDragSelector active={selecting} onDone={() => setSelecting(false)} />
      </MapContainer>
    </section>
  );
}
