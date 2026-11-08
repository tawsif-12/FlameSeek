import type { HotspotRecord } from "../types/api";

/** Stable identities keep repeated FIRMS records from colliding in Cesium. */
export function globePointKey(h: HotspotRecord): string {
  return h.harmonized
    ? `hz:${h.harmonized.event_id}`
    : `hs:${h.sensor}|${h.satellite}|${h.lat}|${h.lon}|${h.acq_datetime}`;
}

export function uniqueGlobePoints(points: HotspotRecord[]): HotspotRecord[] {
  const unique = new Map<string, HotspotRecord>();
  for (const point of points) {
    const key = globePointKey(point);
    if (!unique.has(key)) unique.set(key, point);
  }
  return Array.from(unique.values());
}
