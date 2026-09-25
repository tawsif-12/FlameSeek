import type { BBox } from "../types/api";

export function buildWorldviewUrl({ date, bbox }: { date: string; bbox: BBox }): string {
  const [w, s, e, n] = bbox;
  const layers = "VIIRS_SNPP_Thermal_Anomalies_375m_Day,MODIS_Fires_All";
  return `https://worldview.earthdata.nasa.gov/?t=${date}&v=${w},${s},${e},${n}&l=${layers}`;
}

