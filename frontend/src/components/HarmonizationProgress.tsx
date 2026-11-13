import { useEffect, useState } from 'react';

type Stage = { stage: number; name: string; status: string; reason?: string; seconds?: number; limitations?: Record<string,string> };
type Report = { stages: Stage[]; running?: boolean; finished?: boolean; error?: string; full_harmonization_complete?: boolean; computed_activity_cell_days?: number };
const LABEL: Record<string,string> = {computed:'Computed',partial:'Partial',failed:'Failed',pending:'Queued',running:'Running','awaiting data':'Needs data'};

export default function HarmonizationProgress({ runId }: { runId: string | null }) {
  const [report,setReport]=useState<Report|null>(null);
  const [error,setError]=useState<string|null>(null);
  useEffect(()=>{
    setReport(null); setError(null);
    if (!runId) return;
    const controller=new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response=await fetch(`${import.meta.env.VITE_API_BASE_URL||''}/api/harmonization/${runId}/status`,{signal:controller.signal});
        if (!response.ok) throw new Error('Stage status unavailable');
        const result: Report=await response.json();
        if (controller.signal.aborted) return;
        setReport(result); setError(null);
        if (!result.finished && !result.error) timer=setTimeout(refresh,5000);
      } catch(reason) {
        if (!controller.signal.aborted) { setError(reason instanceof Error?reason.message:'Stage status unavailable'); timer=setTimeout(refresh,10000); }
      }
    }
    void refresh();
    return ()=>{controller.abort();clearTimeout(timer);};
  },[runId]);
  return <details className="harmonization-progress">
    <summary>10-stage harmonization {report?.full_harmonization_complete?'· complete':report?.running?'· processing':'· status'}</summary>
    {!runId && <p>Waiting for a merge run. Refresh FIRMS to start the full workflow.</p>}
    {error && <p role="status">{error}. Retrying…</p>}
    {runId && !report && !error && <p role="status">Loading stage status…</p>}
    {report && <>
      {!report.stages.length && <p>Preparing the background workflow…</p>}
      <ol>{report.stages.map(stage=><li key={stage.stage} data-status={stage.status}>
        <div><strong>{stage.stage}. {stage.name}</strong><span>{LABEL[stage.status]||stage.status}</span></div>
        {stage.reason && <p>{stage.reason}</p>}
        {stage.limitations && <p>{Object.entries(stage.limitations).filter(([,value])=>value!=='applied').map(([name,value])=>`${name.replace(/_/g,' ')}: ${value}`).join('; ')}</p>}
      </li>)}</ol>
      {report.error && <p role="alert">{report.error}</p>}
      <p>{report.computed_activity_cell_days?.toLocaleString()||'0'} cell-days have activity estimates. Event markers remain footprint-merged observations; unavailable corrections are never treated as completed harmonization.</p>
    </>}
  </details>;
}
