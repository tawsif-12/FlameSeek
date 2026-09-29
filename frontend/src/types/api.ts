export type SensorName = "modis" | "viirs_snpp" | "viirs_noaa20" | "viirs_noaa21";
export type AnySensor = SensorName | "goes" | "landsat";
export type BBox = [number, number, number, number];
export type LonLat = [number, number];

export interface GeoJSONGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
}

/** Area of interest: bbox, polygon geometry (drawn or from place search), or radius. */
export interface AOI {
  bbox?: BBox;
  geometry?: GeoJSONGeometry | null;
  center?: LonLat;
  radius_km?: number;
  name?: string;
  kind?: "bbox" | "polygon" | "radius" | "place";
}

export interface GenerateCalendarRequest {
  bbox: BBox;
  start_date: string;
  end_date: string;
  sensors: SensorName[];
}

export interface HotspotRecord {
  lat: number;
  lon: number;
  acq_datetime: string;
  confidence_pct: number;
  frp: number | null;
  sensor: AnySensor;
  satellite: string;
  daynight: string;
  scan_km?: number | null;
  track_km?: number | null;
  brightness_k?: number | null;
  brightness_2_k?: number | null;
  version?: string;
  source?: string;
  location_uncertainty_km?: number | null;
}

export interface CurrentHotspotsResponse {
  hotspots: HotspotRecord[];
  metadata: Record<string, unknown>;
}

export interface HotspotVerification {
  score: number;
  verdict: "strong_satellite_signal" | "needs_review" | "weak_satellite_signal";
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

export interface VerifiedHotspotsResponse {
  hotspots: VerifiedHotspotRecord[];
  metadata: Record<string, unknown>;
}

export interface DataSource {
  group: string;
  name: string;
  description: string;
  url: string;
  access: string;
  last_verified: string;
}

// --- Jobs --------------------------------------------------------------------------

export interface Job<T> {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string;
  error: string | null;
  result: T | null;
}

// --- Places ------------------------------------------------------------------------

export interface PlaceResult {
  name: string;
  category: string;
  type: string;
  addresstype: string;
  bbox: BBox;
  center: LonLat;
  geometry: GeoJSONGeometry | null;
}

export interface Place {
  country: string | null;
  country_code: string | null;
  state: string | null;
  district: string | null;
  city: string | null;
  village: string | null;
  local_name: string | null;
  display_name: string | null;
  precision: string;
  source: string;
  nearest_settlement: { name: string; type: string; distance_km: number } | null;
  land_context: {
    protected_areas: Array<{ name: string; designation?: string | null }>;
    forests: Array<{ name: string }>;
    land_use: string[];
    nearby_heat_sources: Array<{ type: string; name: string; distance_km: number | null }>;
  };
}

// --- Fire events -----------------------------------------------------------------------

export interface Behaviour {
  state: "Onset" | "Intensifying" | "Expanding" | "Persistent" | "Stable" | "Decaying" | "Uncertain";
  label_type: string;
  reasons?: string[];
  metrics?: Record<string, number | string | null>;
  caveat?: string;
}

export interface FireEventSummary {
  event_id: string;
  first_detection: string;
  latest_detection: string;
  duration_hours: number;
  observation_count: number;
  sensors: string[];
  sensor_families: string[];
  satellites: string[];
  total_frp: number;
  max_frp: number | null;
  frp_trend: string | null;
  centroid: { lat: number; lon: number };
  bbox: BBox;
  extent_km2: number;
  max_span_km: number;
  hull: LonLat[];
  association_confidence: number | null;
  association_note: string;
  behaviour: Behaviour;
  behaviour_state: Behaviour["state"];
}

export interface TimelineBin {
  window_start: string;
  detections: number;
  total_frp: number;
  cumulative_extent_km2: number;
  centroid: [number, number];
  sensors: string[];
}

export interface ObservationQuality {
  sensor_agreement: string;
  platforms_available: string[];
  recent_cloud_cover_pct: number | null;
  observation_sufficiency_score: number;
  location_uncertainty_km: number | null;
  uncertainty: string;
  uncertainty_note: string;
  status_if_absent: string;
  provenance: Record<string, unknown>;
}

export interface FireEvent extends Omit<FireEventSummary, "behaviour_state"> {
  timeline: TimelineBin[];
  detections: HotspotRecord[];
  observation_quality: ObservationQuality;
}

export interface EventsResponse {
  events: FireEventSummary[];
  metadata: Record<string, unknown> & { behaviour_counts?: Record<string, number> };
}

// --- Evidence ----------------------------------------------------------------------------

export interface EvidenceCheck {
  name: string;
  kind: "automated" | "imagery" | "manual_review";
  status: string;
  detail?: string;
  review_url?: string | null;
  matches?: Array<Record<string, unknown>>;
  scenes?: Array<{ id: string; datetime: string; cloud_cover_pct: number | null; hours_from_detection: number; thumbnail?: string | null }>;
}

export interface NewsCard {
  headline: string;
  publication: string;
  domain: string;
  provider: string;
  published_at: string | null;
  url: string;
  country: string | null;
  location_mentioned: string | null;
  distance_km: number | null;
  event_type: string;
  geographic_score: number;
  geographic_match: string;
  location_confidence: string;
  temporal_score: number;
  temporal_match: string;
  hours_after_detection: number | null;
  source_reliability_score: number;
  source_reliability: string;
  relevance_score: number;
  match_label: string;
  system_summary: string;
  nlp: {
    event_type: string;
    causes: string[];
    impact: Record<string, number | boolean>;
    affected_area: string[];
    infrastructure_mentioned: string[];
    dates_mentioned: string[];
    times_mentioned: string[];
    locations: { gazetteer_matches: string[]; other_place_mentions: string[] };
  };
}

export interface EvidenceResult {
  subject: Record<string, unknown>;
  observation: { sensor_families: string[]; sensor_agreement: string; location_uncertainty_km: number; provenance: Record<string, unknown> };
  place: Place;
  stages: Array<{ name: string; status: string; detail?: string }>;
  external_evidence: {
    regional_satellite: { checks: EvidenceCheck[]; corroborating_sources: string[] };
    official: { checks: EvidenceCheck[]; matches: Array<Record<string, unknown>>; has_official_match: boolean; note: string };
    news: { articles: NewsCard[]; searched: Record<string, unknown>; note: string };
  };
  inference: {
    final_status: string;
    status_note?: string | null;
    observation_sufficiency?: number | null;
    system_evidence_score: number;
    score_note: string;
    components: Array<{ signal: string; points: number; max: number; notes: string[] }>;
    fire_type_note: string | null;
    uncertainty: string[];
    explanation: string;
    confirmed_label_policy: string;
  };
  source_transparency: Record<string, string>;
  generated_at: string;
}

// --- Outlook: analogues, forecast, exposure ----------------------------------------------------

export interface Analogue {
  event_id: string;
  year: number;
  first_detection: string;
  centroid: { lat: number; lon: number };
  distance: number;
  most_similar_on: string[];
  least_similar_on: string[];
  outcome: {
    duration_hours: number;
    total_detections: number;
    final_extent_km2: number;
    extent_at_matched_age_km2: number;
    expanded_after_matched_age: boolean;
    peak_frp_window_hours_from_start: number | null;
    peak_window_frp: number | null;
    decay_began_hours_from_start: number | null;
    remaining_hours_after_matched_age: number;
    frp_timeline: Array<{ hours: number; frp: number }>;
  };
}

export interface AnalogueResult {
  status: string;
  note?: string;
  method?: string;
  matched_age_hours?: number;
  features_used?: string[];
  candidates: number;
  analogues: Analogue[];
  summary?: Record<string, string | number | number[] | null>;
  ecological_context?: string;
  caveat?: string;
}

export interface ModelMetrics {
  brier: number;
  brier_skill_vs_climatology: number | null;
  auc: number | null;
  probability_of_detection: number | null;
  false_alarm_ratio: number | null;
  critical_success_index: number | null;
  footprint_iou_mean: number | null;
  expected_calibration_error: number;
  reliability: Array<{ bin: string; mean_forecast: number; observed_frequency: number; n: number }>;
  positives: number;
  samples: number;
}

export interface Validation {
  split?: string;
  status: string;
  models?: Record<string, ModelMetrics>;
  train_positives?: number;
  test_positives?: number;
}

export interface ForecastCell {
  lat: number;
  lon: number;
  p: number;
  level: "low" | "moderate" | "high";
}

export interface ForecastHorizon {
  horizon_hours: number;
  valid_from: string;
  valid_to: string;
  status: "ISSUED" | "FORECAST WITHHELD";
  reasons?: string[];
  model_used?: string;
  model_selection?: string;
  cells: ForecastCell[];
  corridor_area_km2?: number;
  wind?: Record<string, number>;
  validation: { temporal: Validation; spatial: Validation };
  training?: { samples: number; positives: number; issue_times: number; years: number[] } | null;
  feature_importance?: Record<string, number> | null;
}

export interface ForecastResult {
  target: string;
  issue_time: string;
  cell_size_deg: number;
  caveat: string;
  inputs_used: string[];
  inputs_not_used: string[];
  horizons: Record<string, ForecastHorizon>;
}

export interface ExposureResult {
  status: string;
  note?: string;
  corridor_cells?: number;
  corridor_area_km2?: number;
  population?: { status: string; population: number | null; dataset?: string; note?: string };
  assets?: Record<string, { label: string; status: string; count?: number; length_km_inside_corridor?: number; items: Array<Record<string, unknown>> }>;
  wording?: string;
  sources?: string[];
  errors?: string[];
}

export interface OutlookResult {
  event_id: string;
  history: { years: number[]; detections: number; radius_km: number; failed_years: number };
  analogues: AnalogueResult;
  forecast: ForecastResult;
  exposure: ExposureResult;
}

// --- Fire Memory -------------------------------------------------------------------------------

export interface MemoryDay {
  date: string;
  harmonized_activity: number;
  harmonized_low: number;
  harmonized_high: number;
  hotspot_count: number;
  modis_count: number;
  viirs_count: number;
  modis_active_cells: number;
  viirs_active_cells: number;
  active_cell_count: number;
  max_frp: number | null;
  anomaly_score: number;
  anomaly_category: string;
  baseline_median: number;
  baseline_method: string;
  sensor_agreement: string;
  observation_status: string;
  observation_display: string;
  sufficiency_score: number;
  cloud_cover_pct: number | null;
}

export interface SeasonalMonth {
  month: number;
  name: string;
  years: number;
  median_activity?: number;
  activity_iqr?: [number, number];
  median_hotspots?: number;
  median_active_days?: number;
  median_frp?: number | null;
  median_spatial_spread_cells_10km?: number;
  median_event_duration_hours?: number | null;
  events_per_year?: number;
  median_share_of_year?: number;
  season_level: string;
}

export interface FireMemoryResult {
  aoi: Record<string, unknown>;
  period: { start: string; end: string; years: number; days: number };
  summary: { total_hotspots: number; total_harmonized_activity: number; peak_day: string | null; high_anomaly_days: number; category_counts: Record<string, number> };
  daily: MemoryDay[];
  monthly: Array<Record<string, number | null>>;
  calendar: { years: number[]; months: string[]; activity: Array<Array<number | null>>; hotspots: Array<Array<number | null>> };
  seasonal_profile: { years: number[]; months: SeasonalMonth[]; peak_months: string[]; active_months: string[]; quiet_months: string[]; note: string };
  current_vs_historical: {
    status: string;
    window?: { start: string; end: string; days: number };
    current?: Record<string, number>;
    historical?: Record<string, number | null>;
    history_years?: number[];
    robust_z?: number;
    overall_category?: string;
    percentile_rank?: number;
    flags: Array<{ flag: string; label: string; detail: string }>;
    note?: string;
  };
  change_points: {
    status: string;
    note?: string;
    method?: string;
    caveat?: string;
    change_points: Array<{ date: string; direction: string; relative_change: number; mean_activity_before: number; mean_activity_after: number; description: string }>;
    segments?: Array<{ start: string; end: string; mean_monthly_activity: number }>;
  };
  critical_periods: Array<{ start_date: string; end_date: string; duration_days: number; max_anomaly: number; avg_hotspot_count: number; total_hotspots: number }>;
  calibration: { status: string; viirs_to_modis_factor: number | null; factor_iqr: [number, number] | null; pairs: number; note: string };
  observation_quality: { counts: Record<string, number>; labels: Record<string, string>; mean_sufficiency_score: number; pct_days_unobservable: number; method: string };
  events: { count: number; multi_detection: number };
  provenance: Record<string, unknown>;
}
