import axios from "axios";
import type { AOI, DataSource, FireMemoryResult, Job, PlaceResult, SensorName } from "../types/api";

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


export async function getDataSources(): Promise<DataSource[]> {
  const { data } = await api.get("/data-sources");
  return data.sources;
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

export function startFireMemory(aoi: AOI, historyYears: number, sensors: SensorName[], comparisonWindowDays: number) {
  return startJob<FireMemoryResult>("/api/fire_memory", { aoi, history_years: historyYears, sensors, comparison_window_days: comparisonWindowDays });
}
