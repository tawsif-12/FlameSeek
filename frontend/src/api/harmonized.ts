import { useEffect, useState } from "react";

/* Harmonized-record data: offline snapshot API (/meta, /fires/active, /events, /detections)
   and site-data/site.json exported by tools/export_site_data.py. Every exported number carries
   a label, a status and the file it came from; uncomputed items are {"status": "awaiting data"}. */

export interface Labelled {
  value: number | null;
  label: string;
  status: string;
  source: string;
  unit?: string;
  interval?: [number, number] | null;
  note?: string;
}

export interface SnapshotMeta {
  window: string;
  data_version: string | null;
  last_observation_time: string | null;
  now?: string;
  now_basis?: string;
  start?: string;
  end?: string;
  n_events?: number;
  status?: string;
}

export interface CalibrationRow {
  version: string;
  n: number | null;
  a: number | null;
  b: number | null;
  a_interval: [number, number] | null;
  b_interval: [number, number] | null;
  status: string;
  fitted: boolean;
  domain: string;
  reason: string | null;
}

export type Awaiting = { status: "awaiting data" };
export interface HeadlineData { data_version: string; raw_detections: Labelled; low_confidence: Labelled; clean_detections: Labelled; events: Labelled }
export interface EnergyData { before: Labelled; after: Labelled; relative_difference: Labelled }
export interface DriftData { rows: { year: number; platform: string; n: number; median_lst_h: number }[]; label: string; nominal_lst_h: number; nominal_note: string; status: string; source: string }
export interface CalibrationData { rows: CalibrationRow[]; model: string; interval: string; why_differ: string; source: string }
export interface GeoData { regions: { region: string; n_cells: number; assignment_counts: Record<string, number>; mean_selected_vza_deg: number | null }[]; figure: string; label: string; status: string; source: string }
export interface NausData { status: string; published_peak?: Labelled; findings?: string[]; checks?: { label: string; before: number; after: number; passed: boolean | null; source: string; n_before?: number; n_after?: number }[]; figure?: string; source?: string }

export interface SiteData {
  exported_utc: string;
  meta: { default_window: string; windows: Record<string, SnapshotMeta> };
  headline: HeadlineData | Awaiting;
  energy: EnergyData | Awaiting;
  drift: DriftData | Awaiting;
  calibration: CalibrationData | Awaiting;
  detection_limits: (Labelled | (Awaiting & { label: string; source: string }))[];
  geo_assignment: GeoData | Awaiting;
  naus: NausData;
  awaiting: { item: string; effect: string; status: string }[];
  translation: { words: Record<"en" | "bn", Record<string, unknown>>; status: string };
  sources: { name: string; url: string; use: string }[];
  regions: Record<string, [number, number, number, number]>;
  intensity_classes_mw: number[];
}

export interface HarmonizedEvent {
  fire_id: string;
  start_time: string;
  end_time: string;
  centroid_lat: number;
  centroid_lon: number;
  platforms_seen: string | null;
  sensor_flag: string | null;
  FRP_MODIS_max: number | null;
  FRP_VIIRS_max: number | null;
  footprint_area_km2: number | null;
  n_detections: number | null;
  translation: Record<"en" | "bn", Record<string, string | string[]>> & { trend_basis?: string };
  footprint?: GeoJSON.Geometry | null;
}

export interface Detection { fire_id: string; lon: number; lat: number; time: string; platform: string; sensor: string; frp: number | null; conf_class: string }
export interface ListResponse<T> extends SnapshotMeta { data: T[]; count: number; limit: number; offset: number; has_more: boolean; basis?: string }

/** The section if it was computed, else null. */
export function computed<T>(v: T | Awaiting): T | null {
  return v && typeof v === "object" && (v as Awaiting).status === "awaiting data" && Object.keys(v as object).length === 1 ? null : (v as T);
}

const BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function snapshotGet<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
  const r = await fetch(`${BASE}${path}${q.toString() ? `?${q}` : ""}`, payload === undefined ? { signal } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body as T;
}

let siteCache: Promise<SiteData> | null = null;
export function loadSiteData(): Promise<SiteData> {
  siteCache ??= fetch("/site-data/site.json").then((r) => {
    if (!r.ok) throw new Error(`site.json ${r.status}`);
    return r.json();
  });
  return siteCache;
}

export function useSiteData() {
  const [data, setData] = useState<SiteData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadSiteData().then(setData).catch((e) => setError(String(e)));
  }, []);
  return { data, error };
}

/** Live /meta; falls back to the exported manifest (flagged) when the API is unreachable. */
export function useSnapshotMeta(window?: string) {
  const { data: site } = useSiteData();
  const [meta, setMeta] = useState<SnapshotMeta | null>(null);
  const [fromApi, setFromApi] = useState(false);
  // Show the exported manifest at once (flagged); replace it with live /meta when the API answers.
  useEffect(() => {
    if (site && !fromApi) setMeta(site.meta.windows[window || site.meta.default_window] ?? null);
  }, [site, window, fromApi]);
  useEffect(() => {
    let alive = true;
    setFromApi(false);
    snapshotGet<SnapshotMeta>("/meta", { window })
      .then((m) => alive && (setMeta(m), setFromApi(true)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [window]);
  return { meta, fromApi };
}
