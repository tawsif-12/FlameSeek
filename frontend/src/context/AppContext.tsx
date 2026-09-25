import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { BBox, GenerateCalendarResponse, SensorName } from "../types/api";

interface AppState {
  bbox: BBox | null;
  setBbox: (bbox: BBox | null) => void;
  startDate: string;
  setStartDate: (value: string) => void;
  endDate: string;
  setEndDate: (value: string) => void;
  sensors: SensorName[];
  setSensors: (value: SensorName[]) => void;
  calendar: GenerateCalendarResponse | null;
  setCalendar: (value: GenerateCalendarResponse | null) => void;
}

const AppContext = createContext<AppState | null>(null);

export const DEFAULT_SENSORS: SensorName[] = ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"];

function isoDateDaysAgo(daysAgo: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [bbox, setBbox] = useState<BBox | null>(null);
  const [startDate, setStartDate] = useState(isoDateDaysAgo(7));
  const [endDate, setEndDate] = useState(isoDateDaysAgo(1));
  const [sensors, setSensors] = useState<SensorName[]>(DEFAULT_SENSORS);
  const [calendar, setCalendar] = useState<GenerateCalendarResponse | null>(null);

  const value = useMemo(
    () => ({ bbox, setBbox, startDate, setStartDate, endDate, setEndDate, sensors, setSensors, calendar, setCalendar }),
    [bbox, startDate, endDate, sensors, calendar],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppContext must be used inside AppProvider");
  return context;
}
