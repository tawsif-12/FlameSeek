import Plot from "react-plotly.js";
import { useAppContext } from "../context/AppContext";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function startOfWeek(date: Date) {
  const next = new Date(date);
  next.setDate(next.getDate() - next.getDay());
  return next;
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

export default function CalendarHeatmap() {
  const { calendar } = useAppContext();
  const daily = calendar?.daily_series ?? [];
  if (!calendar) return null;
  if (daily.length === 0) return <p className="empty-state">No data available for this AOI and date range.</p>;

  const first = new Date(`${daily[0].date}T00:00:00Z`);
  const week0 = startOfWeek(first);
  const weekIndexes = daily.map((row) => {
    const current = new Date(`${row.date}T00:00:00Z`);
    return Math.floor((current.getTime() - week0.getTime()) / (7 * 24 * 60 * 60 * 1000));
  });
  const weekCount = Math.max(...weekIndexes) + 1;
  const x = Array.from({ length: weekCount }, (_, index) => {
    const week = new Date(week0);
    week.setDate(week0.getDate() + index * 7);
    return isoDate(week);
  });
  const z = Array.from({ length: 7 }, () => Array.from<number | null>({ length: weekCount }).fill(null));
  const text = Array.from({ length: 7 }, () => Array.from<string>({ length: weekCount }).fill(""));
  daily.forEach((row, index) => {
    const current = new Date(`${row.date}T00:00:00Z`);
    const day = current.getDay();
    const week = weekIndexes[index];
    z[day][week] = row.active_cell_count;
    text[day][week] = `${row.date}<br>Active cells: ${row.active_cell_count}<br>Hotspots: ${row.hotspot_count}<br>FRP index: ${row.fire_power_index}<br>Anomaly z: ${row.anomaly_score}`;
  });

  return (
    <section className="viz-panel">
      <h2>Daily Active Cells</h2>
      <Plot
        data={[
          {
            type: "heatmap",
            x,
            y: DAY_LABELS,
            z,
            text,
            colorscale: "YlOrRd",
            hovertemplate: "%{text}<extra></extra>",
            xgap: 3,
            ygap: 3,
          },
        ]}
        layout={{
          autosize: true,
          height: 300,
          margin: { l: 60, r: 20, t: 10, b: 40 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          xaxis: { title: "Week starting" },
          yaxis: { autorange: "reversed" },
        }}
        config={{ responsive: true, displayModeBar: false }}
        className="plot"
      />
    </section>
  );
}
