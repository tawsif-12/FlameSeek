import type { HotspotRecord } from "../types/api";

/** Keep raw satellite sightings separate from reconstructed event representatives. */
export function fireInsights(raw: HotspotRecord[], merged: HotspotRecord[], powerPoints: HotspotRecord[], end: number) {
  const powers = powerPoints.map(point => point.frp).filter((power): power is number => typeof power === "number" && Number.isFinite(power) && power >= 0);
  const start = end - 24 * 3600000;
  const bins = Array.from({ length: 12 }, (_, index) => ({ start: start + index * 7200000, end: start + (index + 1) * 7200000, count: 0 }));
  for (const point of raw) {
    const time = Date.parse(point.acq_datetime);
    if (!Number.isFinite(time) || time < start || time > end) continue;
    bins[Math.min(11, Math.floor((time - start) / 7200000))].count++;
  }
  return {
    modis: raw.filter(point => point.sensor === "modis").length,
    viirs: raw.filter(point => point.sensor.startsWith("viirs")).length,
    multipleSatellites: merged.filter(point => new Set(point.harmonized?.platforms.split(";").map(value => value.trim()).filter(Boolean)).size > 1).length,
    maxFrp: powers.length ? powers.reduce((highest, power) => Math.max(highest, power), 0) : null,
    intense: powers.filter(power => power >= 100).length,
    strong: powers.filter(power => power >= 30 && power < 100).length,
    mild: powers.filter(power => power >= 10 && power < 30).length,
    weak: powers.filter(power => power < 10).length,
    unknown: powerPoints.length - powers.length,
    bins,
    hourMax: Math.max(1, ...bins.map(bin => bin.count)),
    topEvents: merged.filter(point => typeof point.harmonized?.footprint_area_km2 === "number" && Number.isFinite(point.harmonized.footprint_area_km2))
      .slice().sort((a, b) => b.harmonized!.footprint_area_km2 - a.harmonized!.footprint_area_km2 || (b.frp ?? -1) - (a.frp ?? -1)).slice(0, 5),
  };
}
