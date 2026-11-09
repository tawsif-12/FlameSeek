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

/** Yield between uploads and cancel unfinished work when a layer changes. */
export function uploadPointBatches<T>(points: readonly T[], add: (point: T) => void, render: () => void, batchSize = 1000) {
  let index = 0;
  let stopped = false;
  let frame = 0;
  function upload() {
    if (stopped) return;
    const end = Math.min(index + batchSize, points.length);
    for (; index < end; index++) add(points[index]);
    render();
    if (index < points.length) frame = requestAnimationFrame(upload);
  }
  frame = requestAnimationFrame(upload);
  return () => { stopped = true; cancelAnimationFrame(frame); };
}

export function toggleObservationLayer<T extends Record<string, boolean>>(layers: T, key: string, satellites: readonly string[]): T {
  const next: Record<string, boolean> = { ...layers, [key]: !layers[key] };
  if (next[key]) {
    if (key === 'Harmonized') for (const satellite of satellites) next[satellite] = false;
    else if (satellites.includes(key)) next.Harmonized = false;
  }
  return next as T;
}
