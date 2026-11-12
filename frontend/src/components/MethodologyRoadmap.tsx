import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const STEPS = [
  {
    title: "Combine satellite views",
    summary: "Use several satellites to see more fires.",
    question: "Why use more than one satellite?",
    answer: "Terra, Aqua, Suomi-NPP and NOAA-20 pass at different times. Combining their observations gives us more chances to spot a fire. Clouds and gaps between passes can still hide fires.",
    color: "#38bdf8",
  },
  {
    title: "Separate facts from estimates",
    summary: "Show what was seen and what was estimated.",
    question: "Does every hotspot mean a wildfire?",
    answer: "No. A hotspot means a satellite detected heat. We label satellite observations, computer estimates and outside reports separately, so you can see what supports each result.",
    color: "#00d9e5",
  },
  {
    title: "Compare fairly over time",
    summary: "Account for changes in satellite pass times.",
    question: "Why does the time of day matter?",
    answer: "A fire can be stronger in the afternoon than in the morning. Satellite pass times also change as orbits age. When the required data is available, we adjust for these differences before comparing years.",
    color: "#b47aff",
  },
  {
    title: "Check against another satellite",
    summary: "Test estimates using observations left out.",
    question: "How can we check whether an estimate works?",
    answer: "We leave one satellite out, make an estimate using the others, then compare it with what the missing satellite actually saw. Test results are shown only when they have been computed.",
    color: "#f5b526",
  },
  {
    title: "Show forecasts only when ready",
    summary: "Hold back forecasts that lack enough support.",
    question: "Why might a forecast be unavailable?",
    answer: "A forecast needs enough observations and must pass checks against past results. If data is missing or the model does not perform well enough, we explain the gap instead of showing an unreliable forecast.",
    color: "#ff754f",
  },
];

export default function MethodologyRoadmap() {
  const [selected, setSelected] = useState(0);
  const active = STEPS[selected];
  const move = (direction: number) => setSelected((index) => (index + direction + STEPS.length) % STEPS.length);

  return (
    <section className="roadmap-outer-wrapper roadmap-compact" aria-labelledby="roadmap-title">
      <header className="roadmap-compact-heading">
        <div>
          <p className="roadmap-compact-eyebrow">How it works</p>
          <h2 id="roadmap-title">From satellite signals to useful fire information</h2>
          <p>Five steps. Select one to learn more.</p>
        </div>
        <span className="roadmap-compact-count">{selected + 1} / {STEPS.length}</span>
      </header>
      <div className="roadmap-compact-steps" aria-label="How we use satellite data">
        {STEPS.map((step, index) => (
          <button
            key={step.title}
            type="button"
            className={`roadmap-compact-step${selected === index ? " is-selected" : ""}`}
            style={{ "--step-color": step.color } as React.CSSProperties}
            aria-pressed={selected === index}
            aria-controls="roadmap-explanation"
            onClick={() => setSelected(index)}
          >
            <span className="roadmap-compact-number">0{index + 1}</span>
            <strong>{step.title}</strong>
            <span>{step.summary}</span>
          </button>
        ))}
      </div>
      <div id="roadmap-explanation" className="roadmap-compact-detail" aria-live="polite">
        <div>
          <h3>{active.question}</h3>
          <p>{active.answer}</p>
        </div>
        <nav aria-label="Browse steps">
          <button type="button" onClick={() => move(-1)} aria-label="Previous step"><ChevronLeft size={18} /></button>
          <button type="button" onClick={() => move(1)} aria-label="Next step"><ChevronRight size={18} /></button>
        </nav>
      </div>
      <p className="roadmap-compact-note">Missing observations mean unknown conditions, not zero fires.</p>
    </section>
  );
}
