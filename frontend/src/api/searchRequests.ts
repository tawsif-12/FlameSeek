/** Pure request lifecycle helpers, shared with Node regression tests. */
export function queryKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(queryKey).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).filter((key) => object[key] !== undefined).sort().map((key) => `${JSON.stringify(key)}:${queryKey(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export class SearchCache<T> {
  entries = new Map<string, { value: T; expires: number; bytes: number }>();
  bytes = 0;
  maxEntries: number;
  maxBytes: number;
  ttl: number;
  now: () => number;
  constructor(maxEntries = 12, maxBytes = 24 * 1024 * 1024, ttl = 30000, now = Date.now) {
    this.maxEntries = maxEntries; this.maxBytes = maxBytes; this.ttl = ttl; this.now = now;
  }
  remove(key: string) {
    const old = this.entries.get(key);
    if (old) { this.bytes -= old.bytes; this.entries.delete(key); }
  }
  get(key: string): T | undefined {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    if (entry.expires <= this.now()) { this.remove(key); return undefined; }
    this.entries.delete(key); this.entries.set(key, entry);
    return entry.value;
  }
  put(key: string, value: T) {
    this.remove(key);
    // Conservative UTF-16 budget, including large footprint coordinate arrays.
    const bytes = JSON.stringify(value).length * 2;
    if (bytes > this.maxBytes) return;
    this.entries.set(key, { value, bytes, expires: this.now() + this.ttl }); this.bytes += bytes;
    while (this.entries.size > this.maxEntries || this.bytes > this.maxBytes) this.remove(this.entries.keys().next().value!);
  }
}

export function scheduleSearch<T>({ key, cache, load, onResult, onError, onSettled, delay = 250 }: {
  key: string; cache: SearchCache<T>; load: (signal: AbortSignal) => Promise<T>;
  onResult: (value: T) => void; onError: (error: Error) => void; onSettled: () => void; delay?: number;
}): () => void {
  const controller = new AbortController();
  const cached = cache.get(key);
  const timer = setTimeout(async () => {
    try {
      const result = cached ?? await load(controller.signal);
      if (!controller.signal.aborted) { if (cached === undefined) cache.put(key, result); onResult(result); }
    } catch (error) {
      if (!controller.signal.aborted) onError(error as Error);
    } finally { if (!controller.signal.aborted) onSettled(); }
  }, cached === undefined ? delay : 0);
  return () => { clearTimeout(timer); controller.abort(); };
}

export function clusterCentroids<T extends { centroid_lon: number; centroid_lat: number }>(events: T[], zoom: number) {
  const step = 90 / 2 ** Math.max(0, zoom);
  const groups = new Map<string, { events: T[]; lon: number; lat: number }>();
  for (const event of events) {
    const key = `${Math.floor(event.centroid_lon / step)},${Math.floor(event.centroid_lat / step)}`;
    const group = groups.get(key) ?? { events: [], lon: 0, lat: 0 };
    group.events.push(event); group.lon += event.centroid_lon; group.lat += event.centroid_lat;
    groups.set(key, group);
  }
  return [...groups].map(([key, group]) => ({ key, events: group.events, lon: group.lon / group.events.length, lat: group.lat / group.events.length }));
}
