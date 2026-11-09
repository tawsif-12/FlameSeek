import { createContext, useContext, useEffect, useMemo, useState, useRef, useCallback } from "react";
import type { ReactNode } from "react";
import type { AOI, FireMemoryResult, SensorName } from "../types/api";
import { areaFromUrl } from '../api/locationRoutes';

interface AppState {
  lockedArea?: boolean;
  aoi: AOI | null;
  setAoi: (aoi: AOI | null) => void;
  sensors: SensorName[];
  setSensors: (value: SensorName[]) => void;
  memory: FireMemoryResult | null;
  setMemory: (value: FireMemoryResult | null) => void;
}

const AppContext = createContext<AppState | null>(null);

export const DEFAULT_SENSORS: SensorName[] = ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"];
const APP_STATE_KEY = "flameseek.analysis-state.v1";

function readSavedState(): { aoi: AOI | null; sensors: SensorName[]; memory: FireMemoryResult | null } {
  const linked = areaFromUrl(window.location.search, window.location.hash);
  try {
    const saved = JSON.parse(localStorage.getItem(APP_STATE_KEY) ?? "null");
    const freshSearch = window.location.pathname === '/search';
    return { aoi: linked ?? (freshSearch ? null : saved?.aoi ?? null), sensors: saved?.sensors?.length ? saved.sensors : DEFAULT_SENSORS, memory: linked || freshSearch ? null : saved?.memory ?? null };
  } catch {
    return { aoi: linked, sensors: DEFAULT_SENSORS, memory: null };
  }
}

export const SENSOR_LABELS: Record<SensorName, string> = {
  modis: "MODIS",
  viirs_snpp: "VIIRS SNPP",
  viirs_noaa20: "VIIRS NOAA-20",
  viirs_noaa21: "VIIRS NOAA-21",
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [saved] = useState(readSavedState);
  const [aoi, setAoi] = useState<AOI | null>(saved.aoi);
  const [sensors, setSensors] = useState<SensorName[]>(saved.sensors);
  const [memory, setMemory] = useState<FireMemoryResult | null>(saved.memory);

  useEffect(() => {
    try { localStorage.setItem(APP_STATE_KEY, JSON.stringify({ aoi, sensors, memory })); }
    catch { /* The live app remains usable if browser storage is unavailable or full. */ }
  }, [aoi, sensors, memory]);

  const value = useMemo(() => ({ aoi, setAoi, sensors, setSensors, memory, setMemory }), [aoi, sensors, memory]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppContext must be used inside AppProvider");
  return context;
}

/** Each location owns its async writes. Unmounted locations cannot overwrite results. */
export function LocationAreaScope({ area, children }: { area: AOI; children: ReactNode }) {
  const parent = useAppContext();
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const saveMemory = useCallback((value: FireMemoryResult | null) => {
    if (alive.current) parent.setMemory(value);
  }, [parent.setMemory]);
  const fixedArea = useCallback(() => {}, []);
  return <AppContext.Provider value={{ ...parent, aoi: area, lockedArea: true, setAoi: fixedArea, setMemory: saveMemory }}>{children}</AppContext.Provider>;
}

/** Bounding box of any AOI shape (used to frame maps and describe the area). */
export function aoiBBox(aoi: AOI): [number, number, number, number] | null {
  if (aoi.bbox) return aoi.bbox;
  if (aoi.center && aoi.radius_km) {
    const [lon, lat] = aoi.center;
    const dLat = aoi.radius_km / 111.32;
    const dLon = aoi.radius_km / (111.32 * Math.max(Math.cos((lat * Math.PI) / 180), 0.01));
    return [lon - dLon, lat - dLat, lon + dLon, lat + dLat];
  }
  if (aoi.geometry) {
    const rings = aoi.geometry.type === "Polygon" ? [(aoi.geometry.coordinates as number[][][])[0]] : (aoi.geometry.coordinates as number[][][][]).map((p) => p[0]);
    const pts = rings.flat();
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }
  return null;
}

/** Client-side mirror of the backend AOI test, used to filter globe layers. */
export function aoiContains(aoi: AOI, lat: number, lon: number): boolean {
  const bbox = aoiBBox(aoi);
  if (!bbox) return true;
  const [w, s, e, n] = bbox;
  if (lon < w || lon > e || lat < s || lat > n) return false;
  if (aoi.center && aoi.radius_km) {
    const [clon, clat] = aoi.center;
    const toRad = Math.PI / 180;
    const h = Math.sin(((lat - clat) * toRad) / 2) ** 2 + Math.cos(lat * toRad) * Math.cos(clat * toRad) * Math.sin(((lon - clon) * toRad) / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h)) <= aoi.radius_km;
  }
  if (aoi.geometry) {
    const polygons = aoi.geometry.type === "Polygon" ? [aoi.geometry.coordinates as number[][][]] : (aoi.geometry.coordinates as number[][][][]);
    return polygons.some((poly) => inRing(lon, lat, poly[0]) && !poly.slice(1).some((hole) => inRing(lon, lat, hole)));
  }
  return true;
}

function inRing(x: number, y: number, ring: number[][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-12) + xi) inside = !inside;
  }
  return inside;
}

export function describeAoi(aoi: AOI): string {
  if (aoi.name) return aoi.name;
  if (aoi.center && aoi.radius_km) return `${aoi.radius_km} km around ${aoi.center[1].toFixed(2)}, ${aoi.center[0].toFixed(2)}`;
  const b = aoiBBox(aoi);
  return b ? `${aoi.geometry ? "Custom polygon" : "Box"} ${b.map((v) => v.toFixed(2)).join(", ")}` : "Area of interest";
}
