import { useAppContext } from "../context/AppContext";

export default function SummaryStats() {
  const { calendar } = useAppContext();
  if (!calendar) return null;

  return (
    <section className="stats-grid">
      <article>
        <span>Total Hotspots</span>
        <strong>{calendar.summary.total_hotspots.toLocaleString()}</strong>
      </article>
      <article>
        <span>Peak Day</span>
        <strong>{calendar.summary.peak_day ?? "None"}</strong>
      </article>
      <article>
        <span>High Anomaly Days</span>
        <strong>{calendar.summary.high_anomaly_days}</strong>
      </article>
      <article>
        <span>Anomaly Basis</span>
        <strong>{String(calendar.metadata.anomaly_basis ?? "FRP")}</strong>
      </article>
    </section>
  );
}
