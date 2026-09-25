import { useState } from "react";
import { generateCalendar, normalizeApiError } from "../api/client";
import { DEFAULT_SENSORS, useAppContext } from "../context/AppContext";
import type { SensorName } from "../types/api";

const SENSOR_LABELS: Record<SensorName, string> = {
  modis: "MODIS",
  viirs_snpp: "VIIRS SNPP",
  viirs_noaa20: "VIIRS NOAA-20",
  viirs_noaa21: "VIIRS NOAA-21",
};

export default function ControlPanel() {
  const { bbox, startDate, setStartDate, endDate, setEndDate, sensors, setSensors, setCalendar } = useAppContext();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const disabled = !bbox || !startDate || !endDate || startDate > endDate || sensors.length === 0 || loading;

  const toggleSensor = (sensor: SensorName) => {
    setSensors(sensors.includes(sensor) ? sensors.filter((item) => item !== sensor) : [...sensors, sensor]);
  };

  const run = async () => {
    if (!bbox) return;
    setLoading(true);
    setError(null);
    try {
      const response = await generateCalendar({ bbox, start_date: startDate, end_date: endDate, sensors });
      setCalendar(response);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="control-panel">
      <div className="field-row">
        <label>
          Start
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          End
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
      </div>
      <div className="sensor-grid">
        {DEFAULT_SENSORS.map((sensor) => (
          <label key={sensor} className="checkbox-label">
            <input type="checkbox" checked={sensors.includes(sensor)} onChange={() => toggleSensor(sensor)} />
            {SENSOR_LABELS[sensor]}
          </label>
        ))}
      </div>
      <button type="button" className="primary-button" disabled={disabled} onClick={run}>
        {loading ? "Fetching and harmonizing fire data from NASA FIRMS..." : "Generate Calendar"}
      </button>
      {bbox ? <p className="meta-text">AOI: {bbox.map((value) => value.toFixed(3)).join(", ")}</p> : <p className="meta-text">Draw a rectangle on the map to choose an AOI.</p>}
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}

