export type FireSensor = "MODIS" | "VIIRS";

export type SampleHotspot = {
  id: string;
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  satellite: string;
  sensor: FireSensor;
  confidence: string;
  frp: number | null;
  day_night: "D" | "N";
  grid_id: string;
  harmonized_activity_index: number;
  anomaly_score: number;
};

export const sampleHotspots: SampleHotspot[] = [
  {
    id: "viirs-bd-dhaka-20260925",
    latitude: 23.7812,
    longitude: 90.4021,
    acq_date: "2026-09-25",
    acq_time: "0935",
    satellite: "Suomi NPP",
    sensor: "VIIRS",
    confidence: "Nominal",
    frp: 18.6,
    day_night: "D",
    grid_id: "23.78_90.40",
    harmonized_activity_index: 1.8,
    anomaly_score: 1.4,
  },
  {
    id: "modis-br-amazon-20260925",
    latitude: -3.117,
    longitude: -60.025,
    acq_date: "2026-09-25",
    acq_time: "1740",
    satellite: "Aqua",
    sensor: "MODIS",
    confidence: "82%",
    frp: 64.2,
    day_night: "D",
    grid_id: "-3.12_-60.03",
    harmonized_activity_index: 2.6,
    anomaly_score: 2.2,
  },
  {
    id: "viirs-au-nt-20260924",
    latitude: -12.4634,
    longitude: 130.8456,
    acq_date: "2026-09-24",
    acq_time: "1422",
    satellite: "NOAA-20",
    sensor: "VIIRS",
    confidence: "Nominal",
    frp: 41.8,
    day_night: "N",
    grid_id: "-12.46_130.85",
    harmonized_activity_index: 3.4,
    anomaly_score: 3.1,
  },
  {
    id: "modis-us-ca-20260923",
    latitude: 38.5816,
    longitude: -121.4944,
    acq_date: "2026-09-23",
    acq_time: "2055",
    satellite: "Terra",
    sensor: "MODIS",
    confidence: "71%",
    frp: 22.9,
    day_night: "D",
    grid_id: "38.58_-121.49",
    harmonized_activity_index: 0.8,
    anomaly_score: 0.6,
  },
  {
    id: "viirs-gr-athens-20260922",
    latitude: 38.05,
    longitude: 23.78,
    acq_date: "2026-09-22",
    acq_time: "0115",
    satellite: "Suomi NPP",
    sensor: "VIIRS",
    confidence: "Nominal",
    frp: 11.4,
    day_night: "N",
    grid_id: "38.05_23.78",
    harmonized_activity_index: 1.2,
    anomaly_score: 1.1,
  },
];
