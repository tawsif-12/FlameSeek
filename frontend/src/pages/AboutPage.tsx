import { Link } from "react-router-dom";
import HarmonizedProvenance from "../components/HarmonizedProvenance";
import "../harmonized.css";


export default function AboutPage() {
  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> About</p>
          <h2>About FlameSeek</h2>
          <p className="lead">FlameSeek harmonizes satellite fire detections from several sensors so fire activity can be compared across places and years.</p>
          <HarmonizedProvenance />
        </header>
      </div>
      <section className="hz-block">
        <h3>Understanding the evidence</h3>
        <p className="hz-lead">A satellite hotspot is an observation, not automatically a confirmed wildfire. Missing observations do not prove that no fire exists. Estimates and forecasts depend on available coverage and supporting evidence.</p>
        <p className="hz-lead"><Link to="/search">Choose a location</Link> to explore Fire Intelligence, Fire Now, the Burning Calendar and Fire DNA. Read the <Link to="/methodology">methodology</Link> for processing steps and limitations.</p>
      </section>
      <section className="hz-block">
        <h3>Acknowledgements</h3>
        <p className="hz-lead">FlameSeek uses NASA FIRMS MODIS and VIIRS observations alongside regional satellite, agency and other evidence sources where available. See <Link to="/data-sources">Sources &amp; Methods</Link> for original provider links.</p>
      </section>
    </main>
  );
}
