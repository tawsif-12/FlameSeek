import axios from "axios";
import type { CurrentHotspotsResponse, CriticalPeriodsResponse, GenerateCalendarRequest, GenerateCalendarResponse, HotspotEvidenceResponse, HotspotRecord, SensorName, VerifiedHotspotsResponse } from "../types/api";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  timeout: 120000,
});

export function normalizeApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (detail?.message) return detail.message;
    if (typeof detail === "string") return detail;
    return error.message;
  }
  return "Unexpected error";
}

export async function generateCalendar(payload: GenerateCalendarRequest): Promise<GenerateCalendarResponse> {
  const { data } = await api.post<GenerateCalendarResponse>("/api/generate_calendar", payload);
  return data;
}

export async function getCriticalPeriods(payload: GenerateCalendarRequest): Promise<CriticalPeriodsResponse> {
  const { data } = await api.post<CriticalPeriodsResponse>("/api/critical_periods", payload);
  return data;
}

export async function getCurrentHotspots(sensors: SensorName[], days = 1, limit = 10000): Promise<CurrentHotspotsResponse> {
  const { data } = await api.get<CurrentHotspotsResponse>("/api/current_hotspots", {
    params: {
      days,
      limit,
      sensors,
    },
    paramsSerializer: { indexes: null },
  });
  return data;
}

export async function getVerifiedHotspots(sensors: SensorName[]): Promise<VerifiedHotspotsResponse> {
  const { data } = await api.get<VerifiedHotspotsResponse>("/api/verified_hotspots", {
    params: {
      days: 1,
      limit: 20,
      sensors,
    },
    paramsSerializer: { indexes: null },
  });
  return data;
}

export async function getHotspotEvidence(payload: HotspotRecord & { refresh?: boolean }): Promise<HotspotEvidenceResponse> {
  const { data } = await api.post<HotspotEvidenceResponse>("/api/hotspot_evidence", payload);
  return data;
}

export async function getDataSources() {
  const { data } = await api.get("/data-sources");
  return data.sources;
}
