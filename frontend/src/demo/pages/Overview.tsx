import { Link } from "react-router-dom";
import DemoGlobe from "../DemoGlobe";
import { C, Card } from "../ui";

const STAGES = [
  { n: "01", to: "/fire-memory", title: "Fire Memory", q: "What normally happened in this area in the past?", foot: "23 yrs · harmonized record", color: C.obs, icon: "M3 5h14M3 10h14M3 15h14" },
  { n: "02", to: "/fire-now", title: "Fire Now", q: "What are satellites observing right now?", foot: "18,432 detections · 24 h", color: C.obs, icon: "M10 2a8 8 0 100 16 8 8 0 000-16zM2 10h16M10 2c3 3 3 13 0 16M10 2c-3 3-3 13 0 16" },
  { n: "03", to: "/fire-identity", title: "Fire Identity", q: "Which observations belong to the same fire event?", foot: "2,915 events reconstructed", color: C.inf, icon: "M4 5l5 4M9 9l6-4M9 9l2 7M4 5h.01M15 5h.01M11 16h.01" },
  { n: "04", to: "/fire-evidence", title: "Fire Evidence", q: "Do other satellites, officials or local reports agree?", foot: "4 independent source types", color: C.ext, icon: "M4 10l4 4 8-9" },
  { n: "05", to: "/fire-past", title: "Fire Past", q: "How did similar historical fires behave?", foot: "k-nearest analogues", color: C.inf, icon: "M10 2a8 8 0 100 16 8 8 0 000-16zM10 6v4l3 2" },
  { n: "06", to: "/fire-future", title: "Fire Future", q: "Where might new activity be detected next?", foot: "6 · 12 · 24 h corridors", color: C.fc, icon: "M3 16c5-1 9-5 13-12M12 4h4v4" },
  { n: "07", to: "/exposure", title: "Exposure", q: "What lies inside the possible activity corridor?", foot: "people · roads · facilities", color: C.fc, icon: "M10 18s6-5.5 6-10a6 6 0 10-12 0c0 4.500 6 10 6 10zM10 6v0" },
];

export default function Overview() {
  return (
    <div className="fs-page" style={{ gap: 16 }}>
      <div className="hero">
        <div>
          <p className="eyebrow">Global fire intelligence · MODIS + VIIRS</p>
          <h1>A satellite hotspot is an <em>observation</em>,<br />not a confirmed wildfire.</h1>
          <p>
            FlameSeek harmonizes 25 years of fire observations from five satellites, reconstructs evolving fire events, checks them against
            regional satellites, official sources and local news, and estimates where new activity may be detected next.
          </p>
          <div className="row">
            <Link to="/fire-now" className="btn primary inline">Open Fire Now →</Link>
            <Link to="/fire-memory" className="btn inline">Build a fire memory for any area</Link>
            <Link to="/fire-evidence/fusion" className="btn inline">How the evidence works</Link>
          </div>
        </div>
        <div className="hero-globe"><DemoGlobe interactive={false} spin stars={false} altitude={17_500_000} lon={78} /></div>
      </div>

      <div className="stages">
        {STAGES.map((s) => (
          <Link key={s.n} to={s.to} className="stage-card">
            <i>{s.n}<svg viewBox="0 0 20 20" fill="none" stroke={s.color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><path d={s.icon} /></svg></i>
            <b>{s.title}</b>
            <p>{s.q}</p>
            <small>{s.foot}</small>
          </Link>
        ))}
      </div>

      <div className="grid" style={{ gridTemplateColumns: "0.75fr 1fr 1fr 1fr 1fr" }}>
        <div style={{ alignSelf: "center" }}>
          <p className="card-h" style={{ lineHeight: 1.6 }}>Every answer keeps four things apart</p>
          <p className="note" style={{ marginTop: 6 }}>Example: fire event FS-BD-2026-0412, East Sundarbans, Bangladesh</p>
        </div>
        <Card accent={C.obs}><p className="card-h" style={{ color: C.obs }}>Observation</p><p className="note">63 thermal detections from 5 sensors over 52 hours. Peak fire power 96 MW. Three passes partly cloud-covered.</p></Card>
        <Card accent={C.inf}><p className="card-h" style={{ color: C.inf }}>Inference</p><p className="note">One evolving fire event, currently <b style={{ color: "var(--text)" }}>expanding</b>. Activity is highly unusual for this place and season.</p></Card>
        <Card accent={C.ext}><p className="card-h" style={{ color: C.ext }}>External evidence</p><p className="note">Himawari-9 thermal anomaly and two matching local news reports within 4 km. No official report yet.</p></Card>
        <Card accent={C.fc}><p className="card-h" style={{ color: C.fc }}>Forecast</p><p className="note">New detections most likely north-east of the event in the next 24 h. Not a prediction of physical fire spread.</p></Card>
      </div>
    </div>
  );
}
