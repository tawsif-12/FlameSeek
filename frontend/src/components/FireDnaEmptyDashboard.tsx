import type { CSSProperties } from "react";

const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function FireDnaEmptyDashboard({ regionName, running }: { regionName: string; running: boolean }) {
  const waiting = running ? "Building from NASA FIRMS…" : "Awaiting analysis";
  return <>
    <section className="dna-identity-row dna-preview">
      <article className="dna-panel dna-identity"><header><b>2.</b><h3>Regional Fire Identity</h3></header><div className="dna-region-title"><span>🔥</span><div><strong>{regionName}</strong><small>{waiting}</small></div></div><div className="dna-metric-grid">{["Peak burning month", "Peak burning season", "Typical annual activity", "Long-term trend"].map((label) => <div key={label}><small>{label}</small><strong>—</strong><em>Generate profile to calculate</em></div>)}</div></article>
      <article className="dna-panel dna-preview-fingerprint"><header><b>4.</b><h3>Fire DNA Fingerprint</h3></header><div className="dna-preview-radar"><i /><i /><i /><span>FIRE<br />DNA</span></div><small>{waiting}</small></article>
    </section>
    <section className="dna-chart-row dna-preview">
      <article className="dna-panel"><header><b>3.</b><h3>Seasonal Fire Activity Pattern</h3></header><div className="dna-preview-bars">{months.map((month, index) => <span key={month} style={{ "--bar": `${20 + ((index * 17) % 54)}%` } as CSSProperties}><i /><small>{month}</small></span>)}</div><p className="dna-interpretation">Monthly medians will appear after the regional analysis completes.</p></article>
      <article className="dna-panel"><header><b>5.</b><h3>Historical Trend</h3></header><div className="dna-preview-trend"><i /><span>{waiting}</span></div><div className="dna-history-stats">{["Highest year", "Lowest year", "Typical activity", "Trend"].map((label) => <div key={label}><small>{label}</small><strong>—</strong></div>)}</div></article>
    </section>
    <section className="dna-analysis-row dna-preview">
      <article className="dna-panel"><header><b>6.</b><h3>Unusual Fire Activity Events</h3></header><div className="dna-preview-rows">{[1, 2, 3, 4].map((row) => <span key={row}><i /><i /><i /></span>)}</div><p className="dna-method">Anomalies are calculated only from comparable historical months.</p></article>
      <article className="dna-panel dna-selected"><header><b>7.</b><h3>Selected Period Details</h3></header><dl>{["Period", "Total hotspots", "Historical median", "Confidence", "Anomaly category"].map((label) => <div key={label}><dt>{label}</dt><dd>—</dd></div>)}</dl><button disabled>⌖ View Hotspots on Map</button></article>
    </section>
    <section className="dna-summary-row dna-preview"><article className="dna-panel dna-summary"><header><b>8.</b><h3>Fire DNA Summary</h3></header><p>{running ? `FlameSeek is assembling ${regionName}'s real satellite fire history.` : `Generate the profile to reveal ${regionName}'s seasonal peak, historical trend, and unusual activity.`}</p><button disabled>💡 What does this mean? <span>+</span></button></article></section>
    <section className="dna-panel dna-reliability dna-preview"><header><b>9.</b><h3>Data Reliability & Export</h3></header><div>{["NASA FIRMS", "Observation period", "Data coverage", "Quality checks", "Static-source filtering", "Uncertainty"].map((label) => <span key={label}><small>{label}</small><strong>Pending analysis</strong></span>)}</div></section>
  </>;
}

