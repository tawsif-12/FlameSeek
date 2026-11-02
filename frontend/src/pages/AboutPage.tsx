import HarmonizedProvenance from "../components/HarmonizedProvenance";
import "../harmonized.css";

/* Placeholder content — to be edited by the team. */
const TEAM = ["[Name 1]", "[Name 2]", "[Name 3]"];

export default function AboutPage() {
  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> About</p>
          <h2>About FlameSeek</h2>
          <p className="lead">[Placeholder — replace with your mission statement.] FlameSeek harmonizes satellite fire detections from several sensors so fire activity can be compared across places and years.</p>
          <HarmonizedProvenance />
        </header>
      </div>
      <section className="methods">
        <h3>Team</h3>
        <div className="method-grid">
          {TEAM.map((name, i) => (
            <article key={name} className="method-card glass-card">
              <span className="method-index" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
              <h4>{name}</h4>
              <p>[Role] · [Affiliation]</p>
              <p>[One or two sentences about this person's part of the project.]</p>
            </article>
          ))}
        </div>
      </section>
      <section className="hz-block">
        <h3>Contact</h3>
        <p className="hz-lead">[Email or contact form link.]</p>
      </section>
      <section className="hz-block">
        <h3>Acknowledgements</h3>
        <p className="hz-lead">[Funders, mentors and data providers — see the data sources on the Methodology page.]</p>
      </section>
    </main>
  );
}
