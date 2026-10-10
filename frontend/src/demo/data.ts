// Illustrative demo data. Nothing here is fetched or computed from real observations.

export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const NOW_LABEL = "22 Mar 2026 · 14:52 UTC";

export const EVENT = {
  id: "FS-BD-2026-0412",
  place: "East Sundarbans, Bagerhat",
  range: "Sharankhola Range · Sundarbans Reserve Forest",
  lon: 89.82,
  lat: 22.12,
  first: "20 Mar 2026 · 07:41 UTC",
  latest: "22 Mar 2026 · 07:52 UTC",
  detections: 63,
  passes: 9,
  score: 88,
  state: "Expanding",
};

export const SENSORS = [
  { name: "MODIS · Terra", count: "2,184", color: "#f2c94c" },
  { name: "MODIS · Aqua", count: "2,906", color: "#f2c94c" },
  { name: "VIIRS · Suomi NPP", count: "4,410", color: "#ef5350" },
  { name: "VIIRS · NOAA-20", count: "4,377", color: "#ef5350" },
  { name: "VIIRS · NOAA-21", count: "4,555", color: "#ef5350" },
];

// [lon, lat, spread in degrees, count]
const CLUSTERS: Array<[number, number, number, number]> = [
  [80, 21.5, 3.6, 520], [77.5, 26.5, 2.4, 160], [84, 19.5, 2, 220], [96.5, 21, 2, 330], [101, 18.5, 2.2, 340],
  [105.5, 13.5, 1.6, 220], [92.3, 22.4, 0.5, 70], [89.82, 22.12, 0.08, 40], [102, 0.5, 1.6, 110], [113.5, -1.5, 2.2, 140],
  [108, 24, 2.4, 110], [22, 7, 6, 520], [33, -8, 5, 300], [-2, 10, 4, 220], [132, -15.5, 3.4, 150], [-55, -11, 6, 320],
  [-90, 16.5, 2, 110], [47, -19, 1.6, 90],
];

export const GLOBE_HOTSPOTS: Array<{ lon: number; lat: number; level: number }> = (() => {
  const r = rng(412);
  const gauss = () => (r() + r() + r() + r() - 2) / 1.15;
  const out: Array<{ lon: number; lat: number; level: number }> = [];
  for (const [lon, lat, spread, count] of CLUSTERS) {
    for (let i = 0; i < count; i++) out.push({ lon: lon + gauss() * spread, lat: lat + gauss() * spread * 0.8, level: r() });
  }
  return out;
})();

export const BD_OUTLINE: Array<[number, number]> = [
  [88.35, 26.6], [88.9, 26.3], [89.1, 26.1], [89.6, 26.2], [89.8, 25.9], [89.85, 25.3], [90.4, 25.15], [91.3, 25.2], [92.0, 25.2],
  [92.4, 25.0], [92.5, 24.9], [92.2, 24.5], [91.9, 24.3], [91.6, 24.1], [91.2, 23.9], [91.15, 23.6], [91.3, 23.2], [91.45, 23.0],
  [91.8, 23.2], [92.0, 23.6], [92.3, 23.7], [92.4, 23.2], [92.6, 22.0], [92.6, 21.4], [92.3, 21.4], [92.2, 21.1], [92.3, 20.7],
  [92.2, 20.6], [92.0, 21.1], [91.9, 21.5], [91.8, 22.2], [91.5, 22.7], [91.2, 22.5], [90.8, 22.3], [90.6, 22.0], [90.3, 21.8],
  [89.9, 21.8], [89.5, 21.7], [89.1, 21.7], [89.0, 22.2], [88.95, 22.8], [88.8, 23.2], [88.6, 23.6], [88.75, 24.2], [88.2, 24.5],
  [88.1, 24.9], [88.45, 25.2], [88.9, 25.2], [88.4, 25.7], [88.15, 26.1],
];

export const BD_CITIES: Array<[string, number, number]> = [
  ["Rangpur", 89.25, 25.75], ["Mymensingh", 90.4, 24.75], ["Sylhet", 91.87, 24.9], ["Rajshahi", 88.6, 24.37], ["Dhaka", 90.4, 23.8],
  ["Khulna", 89.55, 22.82], ["Satkhira", 89.07, 22.72], ["Bagerhat", 89.79, 22.66], ["Barishal", 90.35, 22.7], ["Chattogram", 91.8, 22.35],
];

export const BD_RIVERS: Array<Array<[number, number]>> = [
  [[89.7, 27.3], [89.65, 26.0], [89.75, 24.6], [89.8, 23.8], [90.3, 23.4], [90.6, 22.9], [90.75, 22.0]],
  [[86.6, 25.2], [88.1, 24.6], [88.9, 24.1], [89.8, 23.8]],
  [[92.6, 25.0], [91.3, 24.9], [90.95, 24.1], [90.7, 23.6], [90.6, 22.9]],
  [[91.9, 26.6], [90.4, 26.2], [89.7, 26.0]],
];

export function inPolygon(lon: number, lat: number, poly: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export const YEARS = Array.from({ length: 24 }, (_, i) => 2003 + i);
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Burning calendar: harmonized fire-active cells per month, 2003–2026 (2026 is partial).
export const CALENDAR: number[][] = (() => {
  const r = rng(2003);
  const season = [0.8, 1.6, 9.6, 12.5, 6.4, 0.9, 0.1, 0.05, 0.05, 0.2, 0.4, 0.6];
  return YEARS.map((year, yi) => {
    const lift = (yi >= 11 ? 1.3 : 0.9) * (0.7 + r() * 0.6);
    return season.map((s, m) => {
      if (year === 2026) return m === 0 ? 0.9 : m === 1 ? 2.1 : m === 2 ? 39.4 : -1;
      return +(s * lift * (0.6 + r() * 0.8)).toFixed(1);
    });
  });
})();

export const ANNUAL: number[] = [48, 34, 32, 40, 45, 37, 39, 27, 34, 41, 31, 64, 56, 74, 52, 50, 60, 46, 68, 55, 47, 54, 66];
