import Plot from "react-plotly.js";
import { useAppContext } from "../context/AppContext";

export default function AnomalyTimeSeries() {
  const { calendar } = useAppContext();
  const daily = calendar?.daily_series ?? [];
  if (!calendar || daily.length === 0) return null;

  const shapes = daily
    .filter((row) => row.anomaly_score > 2)
    .map((row) => ({
      type: "rect" as const,
      xref: "x" as const,
      yref: "paper" as const,
      x0: row.date,
      x1: row.date,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(220, 38, 38, 0.22)",
      line: { width: 6, color: "rgba(220, 38, 38, 0.22)" },
    }));

  return (
    <section className="viz-panel">
      <h2>Hotspots and Anomalies</h2>
      <Plot
        data={[
          {
            type: "scatter",
            mode: "lines+markers",
            x: daily.map((row) => row.date),
            y: daily.map((row) => row.fire_power_index),
            name: "FRP-weighted index",
            line: { color: "#2563eb", width: 2 },
          },
          {
            type: "scatter",
            mode: "lines",
            x: daily.map((row) => row.date),
            y: daily.map((row) => row.anomaly_score),
            name: "Anomaly score",
            yaxis: "y2",
            line: { color: "#dc2626", width: 2 },
          },
        ]}
        layout={{
          autosize: true,
          height: 320,
          margin: { l: 55, r: 55, t: 10, b: 45 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          yaxis: { title: "FRP index" },
          yaxis2: { title: "z", overlaying: "y", side: "right" },
          shapes,
          legend: { orientation: "h" },
        }}
        config={{ responsive: true }}
        className="plot"
      />
    </section>
  );
}
