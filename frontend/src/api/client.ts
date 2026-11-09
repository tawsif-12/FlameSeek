import axios from "axios";
import type {
  PlacePipelineSummary,
  AOI,
  CurrentHotspotsResponse,
  DataSource,
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

const globeRequests = new Map<number, Promise<CurrentHotspotsResponse>>();
export function getHarmonizedHotspots(days = 1): Promise<CurrentHotspotsResponse> {
  const pending = globeRequests.get(days);
  if (pending) return pending;
  const request = api.get<CurrentHotspotsResponse>('/api/harmonized_hotspots', {
    params: { days }, timeout: 120000,
  }).then(({ data }) => data).finally(() => globeRequests.delete(days));
  globeRequests.set(days, request);
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

export async function getDataSources(): Promise<DataSource[]> {
  const { data } = await api.get("/data-sources");
  return data.sources;
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
  const { data } = await api.get<{ results: PlaceResult[] }>("/api/places/search", { params: { q, suggest }, signal });
  return data.results;
}

async function startJob<T>(url: string, body?: unknown, params?: Record<string, unknown>): Promise<Job<T>> {
  const { data } = await api.post<Job<T>>(url, body, { params });
  return data;
}

export async function getJob<T>(id: string): Promise<Job<T>> {
  const { data } = await api.get<Job<T>>(`/api/jobs/${id}`);
  return data;
}

/** Poll a background job until it finishes, reporting progress along the way. */
export async function runJob<T>(start: Promise<Job<T>>, onProgress: (job: Job<T>) => void, signal?: { cancelled: boolean }): Promise<T> {
  let job = await start;
  onProgress(job);
  while (job.status === "queued" || job.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, 1500));
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

export async function savedFireMemory(aoi: AOI, historyYears: number, sensors: SensorName[]) {
  const { data } = await api.post<{ result: FireMemoryResult | null }>("/api/fire_memory/saved", { aoi, history_years: historyYears, sensors, comparison_window_days: 30 });
  return data.result;
}

export async function savedPlacePipeline(aoi: AOI, historyYears: number) {
  const { data } = await api.post<{ result: PlacePipelineSummary | null }>("/api/place_pipeline/saved", { aoi, history_years: historyYears });
  return data.result;
}
