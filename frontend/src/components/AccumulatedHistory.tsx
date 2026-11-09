import { useEffect, useState } from 'react';
import { aoiBBox, useAppContext } from '../context/AppContext';

type History = {
  raw_detections: number; reconstructed_events: number; coverage_status: string;
  daily: { day: string; source: string; processing_type: string; detections: number; maximum_detection_frp_mw: number | null }[];
};

export default function AccumulatedHistory() {
  const { aoi } = useAppContext();
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [history, setHistory] = useState<History | null>(null);
  const [message, setMessage] = useState('');
  useEffect(() => {
    setHistory(null);
    if (!aoi) { setMessage('Select a location to see accumulated observations.'); return; }
    const bbox = aoiBBox(aoi);
    if (!bbox) return;
    const controller = new AbortController();
    setMessage('Loading published history…');
    const query = new URLSearchParams();
    if (start) query.set('start', start);
    if (end) query.set('end', end);
    const load = () => fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/pipeline/history?${query}`, {
      method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox, geometry: aoi.geometry, center: aoi.center, radius_km: aoi.radius_km }),
    }).then(async r => { if (!r.ok) throw new Error('Published daily history is unavailable for this selection.'); return r.json(); })
      .then(data => { setHistory(data); setMessage(''); })
      .catch(error => { if (!controller.signal.aborted) setMessage(error.message); });
    void load();
    const timer = window.setInterval(load, 60000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [aoi, start, end]);
  return <section className="glass-card accumulated-history">
    <h3>Accumulated daily fire history</h3>
    <p>Published satellite observations and reconstructed events for the selected boundary.</p>
    <div className="pipeline-date-filters">
      <label>From (UTC) <input type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>Through (UTC) <input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>
    </div>
    {message && <p role="status">{message}</p>}
    {history && <>
      <p><strong>{history.raw_detections.toLocaleString()}</strong> raw observations · <strong>{history.reconstructed_events.toLocaleString()}</strong> reconstructed events</p>
      <p>{history.coverage_status}</p>
      <div className="pipeline-history-table"><table><thead><tr><th>UTC date</th><th>Satellite source</th><th>Processing</th><th>Observations</th><th>Maximum detection FRP (MW)</th></tr></thead>
        <tbody>{history.daily.map(row => <tr key={`${row.day}-${row.source}-${row.processing_type}`}><td>{row.day}</td><td>{row.source}</td><td>{row.processing_type}</td><td>{row.detections.toLocaleString()}</td><td>{row.maximum_detection_frp_mw ?? 'Unavailable'}</td></tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}
