import type { MemoryDay } from "../types/api";

/** Weekly burning-activity calendar, z-score anomalies and a recurrence-based outlook, all computed from the backend's daily series. */

export const Z_THRESHOLD = 2.0;
export const MIN_BASELINE_YEARS = 3;
export const FORECAST_WEEKS = 8;

export interface WeekCell {
  year: number;
  week: number; // 1..52 (week 52 absorbs the last 1-2 days)
  days: number;
  activity: number; // harmonized (consistent-record) detections
  frp: number; // Aqua-equivalent FRP, MW
  hotspots: number;
  modis: number;
  viirs: number;
  activeCells: number;
  agreement: Record<string, number>;
  observation: Record<string, number>;
  mean: number | null;
  sd: number | null;
  z: number | null;
}

export interface Calendar {
  years: number[];
  cells: Array<Array<WeekCell | null>>; // [year index][week - 1]
  anomalies: WeekCell[];
  latest: WeekCell | null;
}

export function weekOfYear(iso: string): { year: number; week: number } {
  const d = new Date(`${iso}T00:00:00Z`);
  const year = d.getUTCFullYear();
  const doy = Math.floor((d.getTime() - Date.UTC(year, 0, 1)) / 86_400_000);
  return { year, week: Math.min(52, Math.floor(doy / 7) + 1) };
}

export function weekDates(year: number, week: number): string {
  const f = (d: Date) => d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  const start = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
  const end = new Date(Date.UTC(year, 0, week === 52 ? 31 : 7 + (week - 1) * 7));
  return `${f(start)} – ${f(end)} ${year}`;
}

const bump = (m: Record<string, number>, k: string) => { m[k] = (m[k] ?? 0) + 1; };

export function buildCalendar(daily: MemoryDay[]): Calendar {
  const map = new Map<string, WeekCell>();
  for (const d of daily) {
    const { year, week } = weekOfYear(d.date);
    const key = `${year}-${week}`;
    let c = map.get(key);
    if (!c) {
      c = { year, week, days: 0, activity: 0, frp: 0, hotspots: 0, modis: 0, viirs: 0, activeCells: 0, agreement: {}, observation: {}, mean: null, sd: null, z: null };
      map.set(key, c);
    }
    c.days += 1;
    c.activity += d.harmonized_activity;
    c.frp += d.frp_aqua_equiv;
    c.hotspots += d.hotspot_count;
    c.modis += d.modis_count;
    c.viirs += d.viirs_count;
    c.activeCells += d.active_cell_count;
    bump(c.agreement, d.sensor_agreement);
    bump(c.observation, d.observation_display || d.observation_status);
  }
  const years = [...new Set([...map.values()].map((c) => c.year))].sort((a, b) => a - b);
  const cells = years.map((y) => Array.from({ length: 52 }, (_, i) => map.get(`${y}-${i + 1}`) ?? null));
  // Rolling baseline: mean and sample SD of the same calendar week over all earlier complete years.
  for (let yi = 0; yi < years.length; yi++) {
    for (let w = 0; w < 52; w++) {
      const c = cells[yi][w];
      if (!c) continue;
      const hist = cells.slice(0, yi).map((row) => row[w]).filter((h): h is WeekCell => !!h && h.days >= 6).map((h) => h.activity);
      if (hist.length < MIN_BASELINE_YEARS) continue;
      const mean = hist.reduce((a, b) => a + b, 0) / hist.length;
      const sd = Math.sqrt(hist.reduce((a, b) => a + (b - mean) ** 2, 0) / (hist.length - 1));
      c.mean = mean;
      c.sd = sd;
      c.z = sd > 1e-9 ? (c.activity - mean) / sd : null;
    }
  }
  const all = cells.flat().filter((c): c is WeekCell => !!c);
  return {
    years,
    cells,
    anomalies: all.filter((c) => c.z !== null && c.z >= Z_THRESHOLD).sort((a, b) => (b.z ?? 0) - (a.z ?? 0)),
    latest: all.length ? all.reduce((a, b) => (b.year > a.year || (b.year === a.year && b.week > a.week) ? b : a)) : null,
  };
}

export interface WeekForecast {
  year: number;
  week: number;
  probability: number; // 0-100
  expected: number; // historical mean activity for that week
  severity: "Low" | "Moderate" | "High" | "Severe";
}

/**
 * Recurrence-based outlook for the whole area: the share of earlier years in which the week reached a "notable burning" level
 * (the lower quartile of the area's non-zero weekly activity), nudged by how far the latest complete weeks sit above their baseline.
 * This is a transparent baseline, not a trained model.
 */
export function buildOutlook(cal: Calendar): { weeks: WeekForecast[]; peak: WeekForecast | null; threshold: number; lift: number } {
  const latest = cal.latest;
  if (!latest || cal.years.length < MIN_BASELINE_YEARS) return { weeks: [], peak: null, threshold: 0, lift: 0 };
  const nonZero = cal.cells.flat().filter((c): c is WeekCell => !!c && c.activity > 0).map((c) => c.activity).sort((a, b) => a - b);
  if (!nonZero.length) return { weeks: [], peak: null, threshold: 0, lift: 0 };
  const threshold = nonZero[Math.floor(nonZero.length * 0.25)];
  const recent = cal.cells[cal.years.indexOf(latest.year)].slice(Math.max(0, latest.week - 3), latest.week).filter((c): c is WeekCell => !!c && c.z !== null && c.days >= 6);
  const lift = recent.length ? Math.max(-2, Math.min(3, recent.reduce((a, c) => a + (c.z ?? 0), 0) / recent.length)) : 0;
  const completeYears = cal.years.filter((y) => y < latest.year);
  const maxMean = Math.max(...Array.from({ length: 52 }, (_, w) => mean(completeYears.map((y) => cal.cells[cal.years.indexOf(y)][w]?.activity ?? 0))), 1e-9);
  const weeks: WeekForecast[] = [];
  for (let k = 1; k <= FORECAST_WEEKS; k++) {
    let week = latest.week + k, year = latest.year;
    if (week > 52) { week -= 52; year += 1; }
    const vals = completeYears.map((y) => cal.cells[cal.years.indexOf(y)][week - 1]?.activity ?? 0);
    const base = Math.min(0.97, Math.max(0.02, (vals.filter((v) => v >= threshold).length + 0.5) / (vals.length + 1)));
    const odds = (base / (1 - base)) * Math.exp(0.35 * lift * Math.exp(-(k - 1) / 4));
    const p = Math.round((odds / (1 + odds)) * 100);
    const expected = mean(vals);
    const rel = expected / maxMean;
    weeks.push({ year, week, probability: p, expected, severity: rel >= 0.75 ? "Severe" : rel >= 0.45 ? "High" : rel >= 0.15 ? "Moderate" : "Low" });
  }
  return { weeks, peak: weeks.reduce((a, b) => (b.probability > a.probability ? b : a)), threshold, lift };
}

function mean(v: number[]) {
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
}
