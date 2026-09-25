export type SensorName = "modis" | "viirs_snpp" | "viirs_noaa20" | "viirs_noaa21";
export type BBox = [number, number, number, number];

export interface GenerateCalendarRequest {
  bbox: BBox;
  start_date: string;
  end_date: string;
  sensors: SensorName[];
}

export interface DailyRecord {
  date: string;
  hotspot_count: number;
  mean_frp: number | null;
  fire_power_index: number;
  active_cell_count: number;
  anomaly_score: number;
  baseline_method: string;
  anomaly_basis: string;
}

export interface CalendarSummary {
  total_hotspots: number;
  peak_day: string | null;
  high_anomaly_days: number;
}

export interface GenerateCalendarResponse {
  daily_series: DailyRecord[];
  summary: CalendarSummary;
  metadata: Record<string, unknown>;
}

export interface HotspotRecord {
  lat: number;
  lon: number;
  acq_datetime: string;
  confidence_pct: number;
  frp: number | null;
  sensor: SensorName;
  satellite: string;
  daynight: string;
}

export interface CurrentHotspotsResponse {
  hotspots: HotspotRecord[];
  metadata: Record<string, unknown>;
}

export interface CriticalPeriod {
  start_date: string;
  end_date: string;
  duration_days: number;
  max_anomaly: number;
  avg_hotspot_count: number;
  total_hotspots: number;
}

export interface CriticalPeriodsResponse {
  periods: CriticalPeriod[];
  metadata: Record<string, unknown>;
}

export interface DataSource {
  name: string;
  description: string;
  url: string;
  last_verified: string;
}
