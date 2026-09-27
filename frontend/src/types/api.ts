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

export interface HotspotEvidenceArticle {
  headline: string;
  publication: string;
  country: string;
  published_at: string;
  location_mentioned: string;
  distance_km: number | null;
  event_type: string;
  relevance_score: number;
  location_score: number;
  time_score: number;
  fire_event_score: number;
  source_reliability_score: number;
  semantic_relevance_score: number;
  summary: string;
  url: string;
  match_label: string;
}

export interface HotspotEvidenceResponse {
  hotspot: HotspotRecord;
  place: Record<string, unknown>;
  stages: Array<{ name: string; status: string; detail?: string }>;
  satellite_evidence: {
    status: string;
    sources: string[];
    evidence: string[];
    worldview_url: string;
  };
  government_evidence: {
    status: string;
    sources: string[];
    evidence: string[];
    note?: string;
  };
  news_evidence: {
    status: string;
    preferred_sources: string[];
    queries: string[];
    gdelt_url: string;
    articles: HotspotEvidenceArticle[];
  };
  fusion: {
    final_status: string;
    system_evidence_score: number;
    weights: Record<string, number>;
    why: string[];
    uncertainty: string[];
    ai_analysis: string;
  };
  source_transparency: {
    satellite_sources: string[];
    news_sources: string[];
    government_sources: string[];
    generated_summary_notice: string;
  };
  cache: { hit: boolean; ttl_seconds: number };
}

export interface HotspotVerification {
  score: number;
  verdict: "confirmed_fire" | "needs_review" | "likely_false_positive";
  evidence: Array<{ source: string; signal: string; weight: number }>;
  warnings: string[];
  imagery_url: string;
  news_url: string;
  national_news_url: string;
  country_code: string | null;
  country_name: string;
  place_name: string;
  next_step: string;
  sensor_family: string;
}

export interface VerifiedHotspotRecord extends HotspotRecord {
  verification: HotspotVerification;
}

export interface CurrentHotspotsResponse {
  hotspots: HotspotRecord[];
  metadata: Record<string, unknown>;
}

export interface VerifiedHotspotsResponse {
  hotspots: VerifiedHotspotRecord[];
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
