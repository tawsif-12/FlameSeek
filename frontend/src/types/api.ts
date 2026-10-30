export type SensorName = "modis" | "viirs_snpp" | "viirs_noaa20" | "viirs_noaa21";
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
  partial?: { fire_case: FireCase; updated_at: string } | null;
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

export type CaseKind = "agricultural_burn" | "wildfire" | "controlled_burn" | "industrial_source" | "building_fire" | "volcanic" | "not_a_fire" | "unknown";

export interface CaseMarker {
  kind: CaseKind;
  reality: string;
  state: "Active" | "Growing" | "Weakening" | "Ended";
  provisional: boolean;
  evidence_checked: boolean;
  updated_at?: string;
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

export interface CasePass {
  witness: string;
  label: string;
  time: string;
  off_nadir_km: number | null;
  in_swath: boolean;
  swath_position: string;
  local_solar_hour: number | null;
  method: string;
  outcome: string;
  outcome_label: string;
  frp_mw?: number;
  detections?: number;
  cloud_cover_pct?: number | null;
  detection_chance?: number;
}

export interface CaseEvidenceItem {
  time: string | null;
  stream: "trigger" | "background" | "A" | "B" | "C";
  source: string;
  kind: "observation" | "background" | "external" | "note";
  summary: string;
  reliability: number;
  votes: Record<string, number>;
  link: string | null;
}

export interface FireCase {
  case_id: string;
  opened_at: string;
  closes_at: string;
  status: "open" | "closed";
  provisional: boolean;
  pending_witnesses: string[];
  answer: {
    is_real: { label: string; basis: string };
    kind: { category: CaseKind; label: string; decided: boolean; basis: string };
    now: { label: CaseMarker["state"]; basis: string };
  };
  category_scores: Array<{ category: CaseKind; label: string; score: number; raw_score: number }>;
  decision_rules: { min_top_score: number; min_lead: number; top: CaseKind; top_score: number; lead: number; passed: boolean };
  satellite_fire_probability: { probability: number; prior: number; passes_used: number; method: string };
  passes: CasePass[];
  next_passes: Array<{ label: string; time: string; swath_position: string }>;
  overpass_method: string;
  overpass_errors: string[];
  geostationary: { status: string; satellite?: string; started?: string; last_seen?: string; duration_hours?: number; detail?: string | null; review_links: EvidenceCheck[] };
  burning_season: { status: string; years_checked?: number; years_with_fire_within_5km?: number; years_with_heat_within_1km?: number; window?: string; note?: string };
  evidence_block: CaseEvidenceItem[];
  explanation: string;
  marker: Omit<CaseMarker, "evidence_checked">;
  situations: Record<string, string>;
  streams: {
    pending: Array<"B" | "C">;
    A: { status: string; passes_observed: number; passes_expected: number };
    B: { status: string };
    C: { status: string; reports: number };
  };
  score_note: string;
}

// --- Outlook: analogues, forecast, exposure ----------------------------------------------------

// --- Fire Memory -------------------------------------------------------------------------------

export interface MemoryDay {
  date: string;
  harmonized_activity: number;
  harmonized_low: number;
  harmonized_high: number;
  detailed_activity: number | null;
  fused_fire_cells: number;
  frp_aqua_equiv: number;
  effort_looks: number;
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
  witness: WitnessResult;
  observation_quality: { counts: Record<string, number>; labels: Record<string, string>; mean_sufficiency_score: number; pct_days_unobservable: number; method: string };
  events: { count: number; multi_detection: number };
  provenance: Record<string, unknown>;
}

export interface WitnessResult {
  summary: {
    witnesses: Record<string, { label: string; detections: number; sensitivity_per_look: number; swath_km: number; looks_per_pass_at_aoi: number }>;
    cleaning: Record<string, number>;
    detection_profile: {
      source: "learned" | "prior";
      profile: { intercept: number; coef_log_frp: number; coef_log_area: number };
      frp50_nadir_mw: number | null;
      frp50_scan_edge_mw: number | null;
      matchups: number;
      matchups_detected_by_modis: number;
      matchup_window: string | null;
      modis_frp_per_viirs_frp: number;
      frp_relation_source: string;
      note: string;
      viirs_noaa_treatment: string;
    };
    modis_fraction_of_viirs_fires: number;
    diurnal: { overall: { peak_hour: number; width_h: number; base: number }; by_month: Record<string, { peak_hour: number; width_h: number; base: number }>; source: string; reference: string; note: string };
    effort: { method: string; cloud_source: string };
    tiers: { consistent_record: string; detailed_layer: string };
    fusion: { method: string; false_alarm_per_look: number; cells_in_aoi: number };
    local_day: string;
  };
  validation: {
    continuity?: Array<{ change: string; date: string; window_months: number; raw_count_ratio: number | null; consistent_record_ratio: number | null; verdict: string | null }>;
    hide_one_witness?: {
      status: string;
      hidden: string;
      note: string;
      cell_days_evaluated?: number;
      hidden_detections?: number;
      auc_fused?: number | null;
      auc_prior_only?: number | null;
      auc_fused_where_other_witnesses_detected?: number | null;
      brier_fused?: number;
      brier_prior_only?: number;
    };
  };
  cell_days_recent: Array<{ cell_lat: number; cell_lon: number; local_day: string; sensors_seen: string[]; detections: Record<string, number>; fire_probability: number; frp_aqua_equiv: number }>;
}
