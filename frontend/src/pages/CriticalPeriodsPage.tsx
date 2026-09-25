import { useState } from "react";
import { getCriticalPeriods, normalizeApiError } from "../api/client";
import WorldviewButton from "../components/WorldviewButton";
import { useAppContext } from "../context/AppContext";
import type { CriticalPeriod } from "../types/api";

type SortKey = "max_anomaly" | "duration_days" | "avg_hotspot_count";

export default function CriticalPeriodsPage() {
  const { bbox, startDate, endDate, sensors } = useAppContext();
  const [periods, setPeriods] = useState<CriticalPeriod[]>([]);
  const [metadata, setMetadata] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("max_anomaly");

  const run = async () => {
    if (!bbox) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getCriticalPeriods({ bbox, start_date: startDate, end_date: endDate, sensors });
      setPeriods(response.periods);
      setMetadata(response.metadata);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="content-page">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">Anomaly threshold: 2 sigma</p>
          <h2>Critical Periods</h2>
        </div>
        <button className="primary-button compact" disabled={!bbox || loading} onClick={run}>
          {loading ? "Analyzing..." : "Find Periods"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {!bbox && <p className="empty-state">Choose an AOI on the calendar page first.</p>}
      {typeof metadata.pct_days_critical === "number" && <p className="meta-text">{metadata.pct_days_critical}% of days in this range were critical.</p>}
      <div className="sort-row">
        <label>
          Sort by
          <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
            <option value="max_anomaly">Max anomaly</option>
            <option value="duration_days">Duration</option>
            <option value="avg_hotspot_count">Average hotspots</option>
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Start</th>
              <th>End</th>
              <th>Days</th>
              <th>Max z</th>
              <th>Total hotspots</th>
              <th>Verify</th>
            </tr>
          </thead>
          <tbody>
            {[...periods].sort((a, b) => b[sortKey] - a[sortKey]).map((period, index) => (
              <tr key={`${period.start_date}-${period.end_date}`} className={index < 3 ? "top-row" : ""}>
                <td>{period.start_date}</td>
                <td>{period.end_date}</td>
                <td>{period.duration_days}</td>
                <td>{period.max_anomaly.toFixed(2)}</td>
                <td>{period.total_hotspots}</td>
                <td>{bbox && <WorldviewButton date={period.start_date} bbox={bbox} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
