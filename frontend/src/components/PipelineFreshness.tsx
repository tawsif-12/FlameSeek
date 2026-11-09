import { useEffect, useState } from 'react';

type Status = {
  status: string;
  last_successful_run?: string;
  latest_observation_time?: string;
  failure?: string;
  latest_published_snapshot?: { start: string; end: string; published_at: string; latest_observations_by_source?: Record<string, string> };
  unavailable_source_days?: { source: string; day: string }[];
};

export default function PipelineFreshness() {
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/pipeline/status`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(setStatus)
      .catch(() => { if (!controller.signal.aborted) setStatus({ status: 'status unavailable' }); });
    void refresh();
    const timer = window.setInterval(refresh, 60000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  if (!status) return null;
  const format = (value?: string) => value ? new Date(value).toLocaleString() : 'awaiting update';
  return <aside className="pipeline-freshness" aria-label="Satellite data freshness">
    <span>Daily data: <strong>{status.status.replace(/_/g, ' ')}</strong></span>
    <span>Last successful update: {format(status.last_successful_run)}</span>
    {status.latest_published_snapshot && <span>Last publication: {format(status.latest_published_snapshot.published_at)}</span>}
    <span>Latest observation: {format(status.latest_observation_time)}</span>
    {status.latest_published_snapshot && <span>Stored dates: {status.latest_published_snapshot.start} – {status.latest_published_snapshot.end} UTC · Coverage may have gaps · Near-real-time</span>}
    {!!status.unavailable_source_days?.length && <span>Unavailable source dates: {[...new Set(status.unavailable_source_days.map(row => row.source))].join(', ')}</span>}
    {status.latest_published_snapshot?.latest_observations_by_source && <details><summary>Satellite freshness</summary>
      {Object.entries(status.latest_published_snapshot.latest_observations_by_source).map(([source, when]) => <div key={source}>{source}: {format(when)}</div>)}
    </details>}
    {status.failure && <span role="status">{status.failure}</span>}
  </aside>;
}
