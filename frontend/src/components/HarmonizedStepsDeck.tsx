import { useEffect, useRef, useState } from "react";
import "../harmonized-card-transitions.css";

interface TransitionPreset {
  name: string;
  forwardOut: string;
  forwardIn: string;
  backwardOut: string;
  backwardIn: string;
  durationMs: number;
}

const TRANSITION_PRESETS: readonly TransitionPreset[] = [
  {
    name: "Push & Slide",
    forwardOut: "pt-page-rotatePushLeft",
    forwardIn: "pt-page-moveFromRight pt-page-ontop",
    backwardOut: "pt-page-rotatePushRight",
    backwardIn: "pt-page-moveFromLeft pt-page-ontop",
    durationMs: 820,
  },
  {
    name: "3D Cube",
    forwardOut: "pt-page-rotateCubeLeftOut pt-page-ontop",
    forwardIn: "pt-page-rotateCubeLeftIn",
    backwardOut: "pt-page-rotateCubeRightOut pt-page-ontop",
    backwardIn: "pt-page-rotateCubeRightIn",
    durationMs: 650,
  },
  {
    name: "Scale & Slide",
    forwardOut: "pt-page-scaleDown",
    forwardIn: "pt-page-moveFromRight pt-page-ontop",
    backwardOut: "pt-page-moveToRight pt-page-ontop",
    backwardIn: "pt-page-scaleUp",
    durationMs: 750,
  },
  {
    name: "Fold & Slide",
    forwardOut: "pt-page-rotateFoldLeft",
    forwardIn: "pt-page-moveFromRightFade",
    backwardOut: "pt-page-moveToRightFade",
    backwardIn: "pt-page-rotateUnfoldLeft",
    durationMs: 750,
  },
  {
    name: "3D Room",
    forwardOut: "pt-page-rotateRoomLeftOut pt-page-ontop",
    forwardIn: "pt-page-rotateRoomLeftIn",
    backwardOut: "pt-page-rotateRoomRightOut pt-page-ontop",
    backwardIn: "pt-page-rotateRoomRightIn",
    durationMs: 850,
  },
  {
    name: "3D Carousel",
    forwardOut: "pt-page-rotateCarouselLeftOut pt-page-ontop",
    forwardIn: "pt-page-rotateCarouselLeftIn",
    backwardOut: "pt-page-rotateCarouselRightOut pt-page-ontop",
    backwardIn: "pt-page-rotateCarouselRightIn",
    durationMs: 850,
  },
  {
    name: "Slide & Fade",
    forwardOut: "pt-page-moveToLeftFade",
    forwardIn: "pt-page-moveFromRightFade",
    backwardOut: "pt-page-moveToRightFade",
    backwardIn: "pt-page-moveFromLeftFade",
    durationMs: 750,
  },
];

interface ActiveTransition {
  outgoing: number;
  outClass: string;
  inClass: string;
}

export default function HarmonizedStepsDeck({ steps }: { steps: readonly [string, string, string][] }) {
  const totalSlides = steps.length + 1; // Slide 0 = Intro title card; Slides 1..N = Steps 01..06
  const [current, setCurrent] = useState(0);
  const [transition, setTransition] = useState<ActiveTransition | null>(null);
  const [presetIndex, setPresetIndex] = useState(0);
  const doneFlagsRef = useRef({ out: false, in: false });
  const timerRef = useRef<number | null>(null);

  function clearTimer() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  function finishTransition() {
    clearTimer();
    setTransition(null);
  }

  useEffect(() => () => clearTimer(), []);

  function goTo(targetIndex: number, direction: "forward" | "backward") {
    if (transition !== null || targetIndex === current) return;

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion) {
      setCurrent(targetIndex);
      setPresetIndex((idx) => (idx + 1) % TRANSITION_PRESETS.length);
      return;
    }

    const preset = TRANSITION_PRESETS[presetIndex % TRANSITION_PRESETS.length];
    const outClass = direction === "forward" ? preset.forwardOut : preset.backwardOut;
    const inClass = direction === "forward" ? preset.forwardIn : preset.backwardIn;

    doneFlagsRef.current = { out: false, in: false };
    setTransition({ outgoing: current, outClass, inClass });
    setCurrent(targetIndex);
    setPresetIndex((idx) => (idx + 1) % TRANSITION_PRESETS.length);

    clearTimer();
    timerRef.current = window.setTimeout(finishTransition, preset.durationMs + 100);
  }

  function goNext() {
    goTo((current + 1) % totalSlides, "forward");
  }

  function goPrev() {
    goTo((current - 1 + totalSlides) % totalSlides, "backward");
  }

  function handleCardClick(event: React.MouseEvent<HTMLElement>) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("details, summary, a, button")) return;
    const selection = window.getSelection?.()?.toString() ?? "";
    if (selection.trim().length > 0) return;
    goNext();
  }

  function handleCardKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("details, summary, a, button")) return;
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowRight") {
      event.preventDefault();
      goNext();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      goPrev();
    }
  }

  function slideClassName(index: number) {
    const isCurrent = index === current;
    const isOutgoing = transition !== null && index === transition.outgoing;
    const classes = ["pt-page", `pt-page-${index}`];
    if (isCurrent || isOutgoing) classes.push("pt-page-current");
    if (isOutgoing && transition) classes.push(transition.outClass);
    else if (isCurrent && transition) classes.push(transition.inClass);
    return classes.join(" ");
  }

  function handleAnimationEnd(index: number, event: React.AnimationEvent<HTMLElement>) {
    if (event.target !== event.currentTarget || !transition) return;
    if (index === transition.outgoing) doneFlagsRef.current.out = true;
    if (index === current) doneFlagsRef.current.in = true;
    if (doneFlagsRef.current.out && doneFlagsRef.current.in) {
      finishTransition();
    }
  }

  return (
    <div className="pt-methods-deck">
      <div className="pt-perspective" aria-live="polite">
        {/* Slide 0: Overview Title Card */}
        <article
          className={slideClassName(0)}
          tabIndex={current === 0 ? 0 : -1}
          aria-hidden={current !== 0 && transition?.outgoing !== 0}
          aria-label="How the harmonized record is built. Click to open step 01."
          onClick={handleCardClick}
          onKeyDown={handleCardKeyDown}
          onAnimationEnd={(e) => handleAnimationEnd(0, e)}
        >
          <div className="pt-card-inner pt-card-intro">
            <span className="pt-card-eyebrow">
              <span className="dot" aria-hidden="true" />
              Harmonized Pipeline · {steps.length} Stages
            </span>
            <h3>How the harmonized record is built</h3>
            <p className="pt-card-intro-sub">
              Six sequential validation, footprint, clustering, gridding, sensor-calibration, and completeness stages turn raw FIRMS alerts into one comparable record.
            </p>
            <span className="pt-card-cta">
              Click this card for Step 01 <span aria-hidden="true">→</span>
            </span>
          </div>
        </article>

        {/* Slides 1..6: Step Cards 01..06 */}
        {steps.map(([title, plain, math], i) => {
          const slideIndex = i + 1;
          const stepNum = String(slideIndex).padStart(2, "0");
          const isLast = slideIndex === steps.length;
          return (
            <article
              key={title}
              className={slideClassName(slideIndex)}
              tabIndex={current === slideIndex ? 0 : -1}
              aria-hidden={current !== slideIndex && transition?.outgoing !== slideIndex}
              aria-label={`Step ${stepNum}: ${title}. Click card for next step.`}
              onClick={handleCardClick}
              onKeyDown={handleCardKeyDown}
              onAnimationEnd={(e) => handleAnimationEnd(slideIndex, e)}
            >
              <div className="pt-card-inner">
                <header className="pt-card-head">
                  <div className="pt-card-step-badge">
                    <span className="method-index" aria-hidden="true">{stepNum}</span>
                    <span className="pt-card-stage-label">
                      Stage {stepNum} of {String(steps.length).padStart(2, "0")}
                    </span>
                  </div>
                  <span className="pt-card-next-hint">
                    {isLast ? "Click card to restart ↺" : `Click card for ${String(slideIndex + 1).padStart(2, "0")} →`}
                  </span>
                </header>

                <div className="pt-card-body">
                  <h4>{title}</h4>
                  <p>{plain}</p>
                </div>

                <footer className="pt-card-footer">
                  <details className="hz-math" onClick={(e) => e.stopPropagation()}>
                    <summary>Show the math</summary>
                    <pre>{math}</pre>
                  </details>
                </footer>
              </div>
            </article>
          );
        })}
      </div>

      <div className="pt-deck-controls" aria-label="Pipeline step navigation">
        <div className="pt-deck-dots" role="tablist" aria-label="Pipeline cards">
          <button
            type="button"
            className="pt-deck-dot"
            aria-current={current === 0 ? "step" : undefined}
            onClick={() => goTo(0, current > 0 ? "backward" : "forward")}
          >
            Overview
          </button>
          {steps.map(([title], i) => {
            const idx = i + 1;
            const num = String(idx).padStart(2, "0");
            return (
              <button
                key={title}
                type="button"
                className="pt-deck-dot"
                title={title}
                aria-label={`Stage ${num}: ${title}`}
                aria-current={current === idx ? "step" : undefined}
                onClick={() => goTo(idx, idx < current ? "backward" : "forward")}
              >
                {num}
              </button>
            );
          })}
        </div>

        <div className="pt-deck-nav-btns">
          <button type="button" className="pt-deck-btn" onClick={goPrev} aria-label="Previous card">
            ← Prev
          </button>
          <button type="button" className="pt-deck-btn" onClick={goNext} aria-label="Next card">
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}

