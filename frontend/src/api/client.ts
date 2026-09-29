import axios from "axios";
import type {
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
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
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

export async function getCurrentHotspots(sensors: SensorName[], days = 1, limit = 10000, date?: string): Promise<CurrentHotspotsResponse> {
  const { data } = await api.get<CurrentHotspotsResponse>("/api/current_hotspots", { params: { days, limit, sensors, date }, ...repeatParams });
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

export async function getEvents(days: number, limit = 4000): Promise<EventsResponse> {
  // A cold world reconstruction can take a few minutes while other analyses run.
  const { data } = await api.get<EventsResponse>("/api/events", { params: { days, limit }, timeout: 420000 });
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

export async function searchPlaces(q: string): Promise<PlaceResult[]> {
  const { data } = await api.get<{ results: PlaceResult[] }>("/api/places/search", { params: { q } });
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

export function startFireMemory(aoi: AOI, historyYears: number, sensors: SensorName[], comparisonWindowDays: number) {
  return startJob<FireMemoryResult>("/api/fire_memory", { aoi, history_years: historyYears, sensors, comparison_window_days: comparisonWindowDays });
}
