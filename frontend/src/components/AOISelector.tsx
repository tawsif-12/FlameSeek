import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet-draw";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import { normalizeApiError, searchPlaces } from "../api/client";
import { aoiBBox, describeAoi, useAppContext } from "../context/AppContext";
import type { AOI, PlaceResult } from "../types/api";

const PLACE_HINTS = ["Country", "State / province", "District", "Forest", "Protected area"];

function aoiToLayer(aoi: AOI): L.Layer | null {
  const style = { color: "#f97316", weight: 2, fillOpacity: 0.08 };
  if (aoi.center && aoi.radius_km) return L.circle([aoi.center[1], aoi.center[0]], { radius: aoi.radius_km * 1000, ...style });
  if (aoi.geometry) return L.geoJSON(aoi.geometry as GeoJSON.Geometry, { style });
  if (aoi.bbox) return L.rectangle([[aoi.bbox[1], aoi.bbox[0]], [aoi.bbox[3], aoi.bbox[2]]], style);
  return null;
}

function DrawTools() {
  const map = useMap();
  const { aoi, setAoi } = useAppContext();
  const drawnRef = useRef<L.FeatureGroup | null>(null);

  useEffect(() => {
    const drawn = new L.FeatureGroup();
    drawnRef.current = drawn;
    map.addLayer(drawn);
    const control = new L.Control.Draw({
      draw: {
        marker: false,
        circlemarker: false,
        polyline: false,
        rectangle: { shapeOptions: { color: "#f97316" } },
        polygon: { allowIntersection: false, shapeOptions: { color: "#f97316" } },
        circle: { shapeOptions: { color: "#f97316" } },
      },
      edit: { featureGroup: drawn, remove: true },
    });
    map.addControl(control);

    const fromLayer = (layer: L.Layer): AOI | null => {
      if (layer instanceof L.Circle) {
        const c = layer.getLatLng();
        return { center: [c.lng, c.lat], radius_km: Math.round((layer.getRadius() / 1000) * 10) / 10, kind: "radius" };
      }
      if (layer instanceof L.Rectangle) {
        const b = layer.getBounds();
        return { bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], kind: "bbox" };
      }
      if (layer instanceof L.Polygon) {
        const geometry = (layer.toGeoJSON() as GeoJSON.Feature<GeoJSON.Polygon>).geometry;
        return { geometry: geometry as AOI["geometry"], kind: "polygon" };
      }
      return null;
    };

    map.on(L.Draw.Event.CREATED, (event: L.LeafletEvent) => {
      const created = event as L.DrawEvents.Created;
      setAoi(fromLayer(created.layer));
    });
    map.on(L.Draw.Event.EDITED, (event: L.LeafletEvent) => {
      (event as L.DrawEvents.Edited).layers.eachLayer((layer) => setAoi(fromLayer(layer)));
    });
    map.on(L.Draw.Event.DELETED, () => setAoi(null));

    return () => {
      map.off(L.Draw.Event.CREATED);
      map.off(L.Draw.Event.EDITED);
      map.off(L.Draw.Event.DELETED);
      map.removeControl(control);
      map.removeLayer(drawn);
    };
  }, [map, setAoi]);

  // Keep the drawn/editable layer in sync with the shared AOI (e.g. after a place search).
  useEffect(() => {
    const drawn = drawnRef.current;
    if (!drawn) return;
    drawn.clearLayers();
    if (!aoi) return;
    const layer = aoiToLayer(aoi);
    if (!layer) return;
    if (layer instanceof L.GeoJSON) layer.eachLayer((child) => drawn.addLayer(child));
    else drawn.addLayer(layer);
    const b = aoiBBox(aoi);
    if (b) map.fitBounds([[b[1], b[0]], [b[3], b[2]]], { padding: [24, 24], maxZoom: 10 });
  }, [aoi, map]);

  return null;
}

export default function AOISelector() {
  const { aoi, setAoi } = useAppContext();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlaceResult[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [radiusKm, setRadiusKm] = useState(25);
  const [picked, setPicked] = useState<PlaceResult | null>(null);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setStatus("Searching OpenStreetMap...");
    try {
      const found = await searchPlaces(query.trim());
      setResults(found);
      setStatus(found.length ? null : "No places found.");
    } catch (error) {
      setStatus(normalizeApiError(error));
    }
  }

  function usePlace(place: PlaceResult) {
    setPicked(place);
    setResults([]);
    setAoi(place.geometry ? { geometry: place.geometry, bbox: place.bbox, name: place.name.split(",").slice(0, 2).join(","), kind: "place" } : { bbox: place.bbox, name: place.name, kind: "place" });
  }

  function useRadius() {
    if (!picked) return;
    setAoi({ center: picked.center, radius_km: radiusKm, name: `${radiusKm} km around ${picked.name.split(",")[0]}`, kind: "radius" });
  }

  return (
    <section className="aoi-selector">
      <form className="aoi-search" onSubmit={search}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search: ${PLACE_HINTS.join(", ")}`} aria-label="Search for a place" />
        <button className="secondary-button" type="submit">Search</button>
      </form>
      {status && <p className="meta-text">{status}</p>}
      {results.length > 0 && (
        <ul className="aoi-results">
          {results.map((r) => (
            <li key={`${r.name}-${r.center.join(",")}`}>
              <button type="button" onClick={() => usePlace(r)}>
                <strong>{r.name.split(",")[0]}</strong>
                <span>{(r.addresstype || r.type).replace(/_/g, " ")} · {r.name.split(",").slice(1, 3).join(",")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <div className="aoi-radius-row">
          <label>
            Radius search (km)
            <input type="number" min={1} max={500} value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))} />
          </label>
          <button className="secondary-button" type="button" onClick={useRadius}>Use radius around {picked.name.split(",")[0]}</button>
        </div>
      )}
      <MapContainer center={[15, 20]} zoom={2} minZoom={2} scrollWheelZoom className="map aoi-map">
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <DrawTools />
      </MapContainer>
      <p className="meta-text">
        {aoi ? <>Selected: <strong>{describeAoi(aoi)}</strong></> : "Search a place or draw a rectangle, polygon or circle with the map tools."}
        {aoi && <button className="link-button" type="button" onClick={() => setAoi(null)}>Clear</button>}
      </p>
    </section>
  );
}
