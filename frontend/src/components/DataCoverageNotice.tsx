/** Coverage cannot be inferred from dates or from the presence of fire detections. */
export default function DataCoverageNotice({
  start,
  end,
  snapshot = false,
  id,
  onClose,
}: {
  start?: string;
  end?: string;
  snapshot?: boolean;
  id?: string;
  onClose?: () => void;
}) {
  return (
    <aside
      id={id}
      className={`glass-card${onClose ? " hz-caution-panel" : ""}`}
      aria-label="Data coverage and missing dates"
      style={{
        position: "relative",
        padding: onClose ? "18px 44px 18px 22px" : "18px 22px",
        margin: "16px 0",
        borderLeft: "4px solid #f59e0b",
        lineHeight: 1.6,
      }}
    >
      {onClose && (
        <button
          type="button"
          className="hz-caution-close"
          onClick={onClose}
          aria-label="Hide missing data notice"
          title="Close notice"
        >
          ×
        </button>
      )}
      <strong>Missing data does not mean zero fires</strong>
      {start && end && <p style={{ margin: "8px 0" }}>{snapshot ? "Snapshot processing window" : "Requested analysis period"}: <b>{start} to {end}</b>. These dates alone do not confirm observations for every day.</p>}
      <p style={{ margin: "8px 0" }}>If only five days of data were supplied, results describe those five days. The remaining dates are unknown, not days with zero fires. A longer selected period does not fill those gaps.</p>
      <p style={{ margin: "8px 0" }}><b>Fire detected:</b> a satellite recorded a fire. <b>No fire detected:</b> observation coverage is confirmed with no detections. <b>Data unavailable:</b> coverage is missing or unconfirmed.</p>
      <p style={{ margin: "8px 0 0" }}>Daily coverage is not verified here. Existing summaries may include zeros for dates without records; do not interpret those zeros as confirmed no-fire days or use incomplete records as whole-year totals, seasonal patterns or forecasts.</p>
    </aside>
  );
}

/** Medium-sized interactive caution triangle trigger placed beside section headings. */
export function CoverageCautionButton({
  open,
  onToggle,
  controlsId,
}: {
  open: boolean;
  onToggle: () => void;
  controlsId?: string;
}) {
  return (
    <button
      type="button"
      className="hz-caution-btn"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={controlsId}
      aria-label={open ? "Hide missing satellite data notice" : "Show missing satellite data caution notice"}
      title={open ? "Hide caution notice" : "Caution: Missing data does not mean zero fires — click to read"}
    >
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"
          fill="currentColor"
          fillOpacity="0.16"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line x1="12" y1="9" x2="12" y2="13.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="12" cy="17" r="1.2" fill="currentColor" stroke="none" />
      </svg>
    </button>
  );
}
