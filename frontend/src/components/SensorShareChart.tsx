const COLORS = ["#38bdf8", "#00f2fe", "#f59e0b", "#ff4d26"];

/** A small SVG keeps the homepage independent of the analysis chart engine. */
export default function SensorShareChart({ counts, labels }: { counts: number[]; labels: string[] }) {
  const total = counts.reduce((sum, value) => sum + value, 0);
  let offset = 0;
  return (
    <svg viewBox="0 0 260 260" width="100%" height="100%" role="img" aria-label="Satellite share of hotspots">
      <title>{total ? labels.map((label, i) => `${label}: ${counts[i].toLocaleString()} hotspots`).join(", ") : "No hotspot observations loaded"}</title>
      <circle cx="130" cy="130" r="90" fill="none" stroke="var(--border)" strokeWidth="34" />
      {counts.map((count, i) => {
        const share = total ? count / total * 100 : 0;
        const start = offset;
        offset += share;
        return share > 0 ? (
          <circle key={labels[i]} cx="130" cy="130" r="90" fill="none" stroke={COLORS[i]} strokeWidth="34"
            pathLength="100" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} transform="rotate(-90 130 130)">
            <title>{labels[i]}: {count.toLocaleString()} ({share.toFixed(1)}%)</title>
          </circle>
        ) : null;
      })}
    </svg>
  );
}
