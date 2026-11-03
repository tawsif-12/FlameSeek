/** Coverage cannot be inferred from dates or from the presence of fire detections. */
export default function DataCoverageNotice({ start, end, snapshot = false }: { start?: string; end?: string; snapshot?: boolean }) {
  return (
    <aside className="glass-card" aria-label="Data coverage and missing dates" style={{ padding: "18px 22px", margin: "16px 0", borderLeft: "4px solid #f59e0b", lineHeight: 1.6 }}>
      <strong>Missing data does not mean zero fires</strong>
      {start && end && <p style={{ margin: "8px 0" }}>{snapshot ? "Snapshot processing window" : "Requested analysis period"}: <b>{start} to {end}</b>. These dates alone do not confirm observations for every day.</p>}
      <p style={{ margin: "8px 0" }}>If only five days of data were supplied, results describe those five days. The remaining dates are unknown, not days with zero fires. A longer selected period does not fill those gaps.</p>
      <p style={{ margin: "8px 0" }}><b>Fire detected:</b> a satellite recorded a fire. <b>No fire detected:</b> observation coverage is confirmed with no detections. <b>Data unavailable:</b> coverage is missing or unconfirmed.</p>
      <p style={{ margin: "8px 0 0" }}>Daily coverage is not verified here. Existing summaries may include zeros for dates without records; do not interpret those zeros as confirmed no-fire days or use incomplete records as whole-year totals, seasonal patterns or forecasts.</p>
    </aside>
  );
}
