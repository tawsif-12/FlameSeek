import axios from "axios";
import type {
  PlacePipelineSummary,
  AOI,
  CurrentHotspotsResponse,
  EventsResponse,
  EvidenceResult,
  FireEvent,
  FireMemoryResult,
  Job,
  OutlookResult,
  PlaceResult,
  SensorName,
  VerifiedHotspotsResponse,
} from "../types/api";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 180000,
});

export function normalizeApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (detail?.message) return detail.message;
    if (typeof detail === "string") return detail;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}

const repeatParams = { paramsSerializer: { indexes: null } };

const globeRequests = new Map<string, Promise<CurrentHotspotsResponse>>();
export function getHarmonizedHotspots(days = 1, bbox?: [number, number, number, number]): Promise<CurrentHotspotsResponse> {
  const key = JSON.stringify([days, bbox]);
  const pending = globeRequests.get(key);
  if (pending) return pending;
  const request = api.get<CurrentHotspotsResponse>('/api/harmonized_hotspots', {
    params: { days, ...(bbox ? { bbox: bbox.join(',') } : {}) }, timeout: 120000,
  }).then(({ data }) => data).finally(() => globeRequests.delete(key));
  globeRequests.set(key, request);
  return request;
}

export async function getCurrentHotspots(sensors: SensorName[], days = 1, limit = 10000, date?: string, includeDemo = false): Promise<CurrentHotspotsResponse> {
  const { data } = await api.get<CurrentHotspotsResponse>("/api/current_hotspots", { params: { days, limit, sensors, date, include_demo: includeDemo }, timeout: 120000, ...repeatParams });
  return data;
}

/** Live FIRMS hotspots inside a box (west,south,east,north) for the last `days` days (max 5). */
export async function getHotspotsInBox(bbox: [number, number, number, number], days = 5, limit = 20000): Promise<CurrentHotspotsResponse> {
  const { data } = await api.get<CurrentHotspotsResponse>("/api/current_hotspots", { params: { bbox: bbox.map((v) => v.toFixed(4)).join(","), days, limit }, timeout: 120000 });
  return data;
}

export async function getVerifiedHotspots(sensors: SensorName[]): Promise<VerifiedHotspotsResponse> {
  const { data } = await api.get<VerifiedHotspotsResponse>("/api/verified_hotspots", { params: { days: 1, limit: 20, sensors }, ...repeatParams });
  return data;
}

export async function getEvents(days: number, limit = 4000, includeDemo = false): Promise<EventsResponse> {
  // A cold world reconstruction can take a few minutes while other analyses run.
  const { data } = await api.get<EventsResponse>("/api/events", { params: { days, limit, include_demo: includeDemo }, timeout: 420000 });
  return data;
}

export async function lookupEvent(sensor: string, lat: number, lon: number, acqDatetime: string): Promise<string> {
  const { data } = await api.get<{ event_id: string }>("/api/events/lookup", { params: { sensor, lat, lon, acq_datetime: acqDatetime } });
  return data.event_id;
}

export async function getEvent(eventId: string): Promise<FireEvent> {
  const { data } = await api.get<FireEvent>(`/api/events/${eventId}`);
  return data;
}

export async function searchPlaces(q: string, signal?: AbortSignal, suggest = false): Promise<PlaceResult[]> {
  const { data } = await api.get<{ results: PlaceResult[] }>("/api/places/search", { params: { q, suggest }, signal, headers: { "Cache-Control": "no-cache" } });
  return data.results;
}

// Repeated navigation and StrictMode mounts share identical analysis requests.
const analysisStarts = new Map<string, { started: number; request: Promise<Job<unknown>>; jobId?: string }>();
const jobReads = new Map<string, Promise<Job<unknown>>>();
export async function resolvePlace(placeId: string, signal?: AbortSignal): Promise<PlaceResult | null> {
  const { data } = await api.get<{ result: PlaceResult | null }>("/api/places/resolve", { params: { place_id: placeId }, signal, headers: { "Cache-Control": "no-cache" } });
  return data.result;
}

async function startJob<T>(url: string, body?: unknown, params?: Record<string, unknown>): Promise<Job<T>> {
  const reusable = (url === "/api/fire_memory" || url === "/api/place_pipeline") && !(body as { refresh?: boolean } | undefined)?.refresh;
  const key = JSON.stringify([url, body, params]);
  const existing = analysisStarts.get(key);
  if (reusable && existing && Date.now() - existing.started < 30000) return existing.request as Promise<Job<T>>;
  const request = api.post<Job<T>>(url, body, { params }).then(({ data }) => data);
  if (reusable) {
    for (const [oldKey, value] of analysisStarts) if (Date.now() - value.started >= 30000) analysisStarts.delete(oldKey);
    analysisStarts.set(key, { started: Date.now(), request });
    void request.then((job) => {
      const entry = analysisStarts.get(key);
      if (entry?.request === request) entry.jobId = job.id;
    }).catch(() => { if (analysisStarts.get(key)?.request === request) analysisStarts.delete(key); });
  }
  return request;
}

export async function getJob<T>(id: string): Promise<Job<T>> {
  const existing = jobReads.get(id);
  if (existing) return existing as Promise<Job<T>>;
  const request = api.get<Job<T>>(`/api/jobs/${id}`, { timeout: 15000 }).then(({ data }) => {
    for (const [key, entry] of analysisStarts) {
      if (entry.jobId !== id) continue;
      if (data.status === "failed") analysisStarts.delete(key);
      else if (data.status === "completed") entry.request = Promise.resolve(data);
    }
    return data;
  }).finally(() => jobReads.delete(id));
  jobReads.set(id, request);
  return request;
}

/** Poll a background job until it finishes, reporting progress along the way. */
export async function runJob<T>(start: Promise<Job<T>>, onProgress: (job: Job<T>) => void, signal?: { cancelled: boolean }): Promise<T> {
  let job = await start;
  onProgress(job);
  let polls = 0;
  while (job.status === "queued" || job.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, polls++ === 0 ? 150 : 1500));
    if (signal?.cancelled) throw new Error("cancelled");
    job = await getJob<T>(job.id);
    onProgress(job);
  }
  if (job.status === "failed" || job.result === null) throw new Error(job.error ?? "Analysis failed");
  return job.result;
}

export function startEvidence(eventId: string, refresh = false) {
  return startJob<EvidenceResult>(`/api/events/${eventId}/evidence`, undefined, { refresh });
}

export function startOutlook(eventId: string, years = 8) {
  return startJob<OutlookResult>(`/api/events/${eventId}/outlook`, undefined, { years });
}

export function startFireMemory(aoi: AOI, historyYears: number, sensors: SensorName[], comparisonWindowDays: number, endDate?: string) {
  return startJob<FireMemoryResult>("/api/fire_memory", { aoi, history_years: historyYears, sensors, comparison_window_days: comparisonWindowDays, end_date: endDate });
}

/** FlameSeek pipeline for one place: footprints, events and energy-conserving grid over its history. */
export function startPlacePipeline(aoi: AOI, historyYears: number) {
  return startJob<PlacePipelineSummary>("/api/place_pipeline", { aoi, history_years: historyYears });
}

export async function savedFireMemory(aoi: AOI, historyYears: number, sensors: SensorName[], comparisonWindowDays = 30) {
  const { data } = await api.post<{ result: FireMemoryResult | null }>("/api/fire_memory/saved", { aoi, history_years: historyYears, sensors, comparison_window_days: comparisonWindowDays });
  return data.result;
}

export async function savedPlacePipeline(aoi: AOI, historyYears: number) {
  const { data } = await api.post<{ result: PlacePipelineSummary | null }>("/api/place_pipeline/saved", { aoi, history_years: historyYears });
  return data.result;
}
