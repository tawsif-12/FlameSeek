import type { FireMemoryResult, PlacePipelineSummary } from '../types/api';

export function SummaryMetric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="intelligence-metric"><h3>{label}</h3><strong>{value}</strong><p>{note}</p></article>;
}

/** Only positive recorded counts are plotted: padded calendar zeros cannot prove coverage. */
export function observedTimeline(memory: FireMemoryResult | null, pipeline: PlacePipelineSummary | null) {
  if (pipeline) return pipeline.monthly.filter(row => row.n_events > 0).map(row => ({
    date: `${row.year}-${String(row.month).padStart(2, '0')}`, count: row.n_events,
  })).sort((a, b) => a.date.localeCompare(b.date));
  const months = new Map<string, number>();
  for (const day of memory?.daily ?? []) {
    if (day.hotspot_count > 0) months.set(day.date.slice(0, 7), (months.get(day.date.slice(0, 7)) ?? 0) + day.hotspot_count);
  }
  return [...months].map(([date, count]) => ({ date, count })).sort((a, b) => a.date.localeCompare(b.date));
}

export function ActivityTimeline({ memory, pipeline, loading }: { memory: FireMemoryResult | null; pipeline: PlacePipelineSummary | null; loading: boolean }) {
  const all = observedTimeline(memory, pipeline);
  const rows = all.slice(-24);
  const max = Math.max(1, ...rows.map(row => row.count));
  return <section className="intelligence-timeline" aria-label="Fire activity timeline">
    <header><div><h3>Fire activity timeline</h3><p>{pipeline ? 'Reconstructed events' : 'Recorded detections'} by month · available records only</p></div><span>{all.length > 24 ? 'Latest 24 recorded months' : `${rows.length} months with activity`}</span></header>
    {rows.length ? <div className="intelligence-bars" role="list" aria-label="Recorded monthly activity">{rows.map(row => <div key={row.date} role="listitem" aria-label={`${row.date}: ${row.count} ${pipeline ? 'events' : 'detections'}`}>
      <span>{row.count.toLocaleString()}</span><i style={{ height: `${Math.max(2, row.count / max * 100)}%` }} /><time>{row.date}</time>
    </div>)}</div> : <p className="intelligence-empty" role="status">{loading ? 'Loading recorded activity…' : memory || pipeline ? 'No positive detection records are available to plot. Coverage must be checked before interpreting gaps.' : 'Historical output is unavailable. The timeline will appear when processed records are available.'}</p>}
    <p className="intelligence-note">Only months with recorded activity are plotted. Omitted dates are unknown; selecting a longer history does not create missing observations.</p>
  </section>;
}
