import AnomalyTimeSeries from "../components/AnomalyTimeSeries";
import CalendarHeatmap from "../components/CalendarHeatmap";
import ControlPanel from "../components/ControlPanel";
import MapAOI from "../components/MapAOI";
import SummaryStats from "../components/SummaryStats";
import WorldviewButton from "../components/WorldviewButton";
import { useAppContext } from "../context/AppContext";

export default function HomePage() {
  const { bbox, calendar } = useAppContext();
  const peakDay = calendar?.summary.peak_day;

  return (
    <main className="page-grid">
      <div className="left-column">
        <MapAOI />
        <ControlPanel />
      </div>
      <div className="right-column">
        <SummaryStats />
        {peakDay && bbox && (
          <section className="action-band">
            <span>Peak activity day: {peakDay}</span>
            <WorldviewButton date={peakDay} bbox={bbox} />
          </section>
        )}
        <CalendarHeatmap />
        <AnomalyTimeSeries />
        {!calendar && <p className="empty-state">Draw an area of interest, choose dates, and generate a harmonized fire calendar.</p>}
      </div>
    </main>
  );
}

