import { useId, useState } from "react";
import type { DriftData } from "../api/harmonized";
import "../animated-charts.css";

export interface IntervalChartRow {
  label: string;
  value: number;
  lo?: number | null;
  hi?: number | null;
  status: string;
  colour: string;
  note?: string;
}

interface TooltipState {
  leftPct: number;
  topPct: number;
  heading: string;
  lines: string[];
}

const S1 = "#3987e5";
const S2 = "#d95926";
const hhmm = (h: number) => `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;

function niceLinearTicks(rawMin: number, rawMax: number, desired = 6) {
  const span = rawMax - rawMin || 1;
  const pad = span * 0.14;
  const minBound = rawMin - pad;
  const maxBound = rawMax + pad;
  const roughStep = (maxBound - minBound) / Math.max(desired - 1, 2);
  const mag = 10 ** Math.floor(Math.log10(roughStep));
  const norm = roughStep / mag;
  const stepBase = norm <= 1.2 ? 1 : norm <= 2.2 ? 2 : norm <= 5.5 ? 5 : 10;
  const step = stepBase * mag;
  const lo = Math.floor(minBound / step) * step;
  const hi = Math.ceil(maxBound / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step * 0.25; v += step) {
    ticks.push(Number(v.toPrecision(6)));
  }
  return { lo, hi, ticks };
}

function logScaleTicks(rows: IntervalChartRow[], reference?: number) {
  const vals = rows.flatMap((r) => [r.value, r.lo ?? r.value, r.hi ?? r.value]);
  if (reference !== undefined && reference > 0) vals.push(reference);
  const lo = Math.min(...vals) / 1.5;
  const hi = Math.max(...vals) * 1.5;
  const ticks: number[] = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    [1, 2, 5].forEach((m) => {
      const v = m * 10 ** e;
      if (v >= lo && v <= hi) ticks.push(v);
    });
  }
  return { lo, hi, ticks };
}

export function AnimatedDriftChart({
  d,
  fmt,
  children,
}: {
  d: DriftData;
  fmt: (n: number, d?: number) => string;
  children?: React.ReactNode;
}) {
  const uid = useId().replace(/:/g, "");
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const years = Array.from(new Set(d.rows.map((r) => r.year))).sort();
  const platforms = Array.from(new Set(d.rows.map((r) => r.platform))).reverse();
  const colours = [S1, S2];

  const xs = d.rows.map((r) => r.median_lst_h).concat(d.nominal_lst_h);
  const tickMin = Math.floor(Math.min(...xs));
  const tickMax = Math.ceil(Math.max(...xs));
  const ticks: number[] = [];
  for (let h = tickMin; h <= tickMax; h++) ticks.push(h);

  const xMin = Math.min(...xs) - 0.55;
  const xMax = Math.max(...xs) + 0.55;

  const W = 940;
  const rowStep = 48;
  const padL = 96;
  const padR = 34;
  const padT = 34;
  const padB = 38;
  const H = padT + Math.max(platforms.length, 1) * rowStep + padB;
  const plotW = W - padL - padR;

  const toX = (h: number) => padL + ((h - xMin) / (xMax - xMin)) * plotW;
  const toY = (rowIdx: number) => padT + (rowIdx + 0.5) * rowStep;
  const refX = toX(d.nominal_lst_h);

  return (
    <div className="glass-card hz-chart-card anim-chart-card">
      <div className="anim-chart-legend">
        {years.map((y, i) => (
          <span key={y}>
            <span className="hz-sw" style={{ background: colours[i % colours.length] }} />
            {y}
          </span>
        ))}
        <span>┆ design crossing {hhmm(d.nominal_lst_h)}</span>
        <span className="anim-live-pill">
          <span className="anim-live-dot" aria-hidden="true" />
          Live orbit drift
        </span>
      </div>

      <div className="anim-svg-wrap" onMouseLeave={() => setTooltip(null)}>
        <svg
          className="anim-svg-chart"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Animated orbit drift chart comparing ${years.join(" vs ")} median detection times across satellite platforms`}
        >
          <defs>
            <linearGradient id={`drift-grad-fwd-${uid}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={S1} />
              <stop offset="50%" stopColor="#6ad7ff" />
              <stop offset="100%" stopColor={S2} />
            </linearGradient>
            <linearGradient id={`drift-grad-rev-${uid}`} x1="100%" y1="0%" x2="0%" y2="0%">
              <stop offset="0%" stopColor={S1} />
              <stop offset="50%" stopColor="#6ad7ff" />
              <stop offset="100%" stopColor={S2} />
            </linearGradient>
          </defs>

          {/* Vertical grid lines and hour labels */}
          {ticks.map((h) => {
            const gx = toX(h);
            return (
              <g key={h}>
                <line x1={gx} y1={padT - 8} x2={gx} y2={H - padB + 4} className="anim-grid-line" />
                <text x={gx} y={H - 12} textAnchor="middle" className="anim-axis-text">
                  {hhmm(h)}
                </text>
              </g>
            );
          })}

          {/* Design crossing reference line */}
          <line x1={refX} y1={padT - 10} x2={refX} y2={H - padB + 4} className="anim-ref-line" />
          <text x={refX} y={padT - 16} textAnchor="middle" className="anim-ref-label">
            {hhmm(d.nominal_lst_h)} DESIGN
          </text>

          {/* Satellite platform rows */}
          {platforms.map((platform, rowIdx) => {
            const cy = toY(rowIdx);
            const pts = years
              .map((yr, yi) => {
                const match = d.rows.find((r) => r.platform === platform && r.year === yr);
                return match ? { ...match, yearIdx: yi, colour: colours[yi % colours.length] } : null;
              })
              .filter((x): x is NonNullable<typeof x> => x !== null);

            const hasDriftSpan = pts.length >= 2;
            const pFirst = hasDriftSpan ? pts[0] : null;
            const pLast = hasDriftSpan ? pts[pts.length - 1] : null;
            const x1 = pFirst ? toX(pFirst.median_lst_h) : 0;
            const x2 = pLast ? toX(pLast.median_lst_h) : 0;
            const forward = x2 >= x1;
            const deltaMin = pFirst && pLast ? Math.round((pLast.median_lst_h - pFirst.median_lst_h) * 60) : 0;
            const spanPx = Math.abs(x2 - x1);

            return (
              <g key={platform} className="anim-hit-row">
                <rect
                  x={padL}
                  y={cy - rowStep / 2 + 2}
                  width={plotW}
                  height={rowStep - 4}
                  rx={6}
                  className="anim-row-highlight"
                />
                <line x1={padL} y1={cy} x2={W - padR} y2={cy} className="anim-row-guide" />
                <text x={padL - 12} y={cy + 4} textAnchor="end" className="anim-row-label">
                  {platform}
                </text>

                {hasDriftSpan && pFirst && pLast && (
                  <>
                    {/* Base gradient drift track */}
                    <line
                      x1={x1}
                      y1={cy}
                      x2={x2}
                      y2={cy}
                      stroke={`url(#drift-grad-${forward ? "fwd" : "rev"}-${uid})`}
                      strokeWidth={2.5}
                      strokeOpacity={0.55}
                    />
                    {/* Animated continuous directional stream */}
                    <line
                      x1={x1}
                      y1={cy}
                      x2={x2}
                      y2={cy}
                      stroke={forward ? "#ff9e70" : "#7ee3ff"}
                      strokeWidth={2.5}
                      strokeOpacity={0.85}
                      className={forward ? "anim-flow-forward" : "anim-flow-backward"}
                    />
                    {/* Traveling orbital drift tracer orb (continuous SVG animate loop) */}
                    {spanPx > 14 && (
                      <g>
                        <circle cy={cy} r={7} fill={forward ? "#ff9e70" : "#7ee3ff"} opacity={0.28}>
                          <animate
                            attributeName="cx"
                            values={`${x1};${x2};${x2}`}
                            keyTimes="0;0.78;1"
                            dur="3.4s"
                            begin={`${rowIdx * 0.45}s`}
                            repeatCount="indefinite"
                          />
                          <animate
                            attributeName="opacity"
                            values="0;0.42;0.38;0"
                            keyTimes="0;0.1;0.78;1"
                            dur="3.4s"
                            begin={`${rowIdx * 0.45}s`}
                            repeatCount="indefinite"
                          />
                        </circle>
                        <circle cy={cy} r={3.2} fill="#ffffff">
                          <animate
                            attributeName="cx"
                            values={`${x1};${x2};${x2}`}
                            keyTimes="0;0.78;1"
                            dur="3.4s"
                            begin={`${rowIdx * 0.45}s`}
                            repeatCount="indefinite"
                          />
                          <animate
                            attributeName="opacity"
                            values="0;1;1;0"
                            keyTimes="0;0.1;0.78;1"
                            dur="3.4s"
                            begin={`${rowIdx * 0.45}s`}
                            repeatCount="indefinite"
                          />
                        </circle>
                      </g>
                    )}

                    {/* Drift delta micro-badge for wide orbit shifts */}
                    {spanPx > 110 && (
                      <text x={(x1 + x2) / 2} y={cy + 16} textAnchor="middle" className="anim-delta-badge">
                        {deltaMin >= 0 ? `+${deltaMin} min drift →` : `← ${deltaMin} min drift`}
                      </text>
                    )}
                  </>
                )}

                {/* Year point markers with continuous sonar rings */}
                {pts.map((pt) => {
                  const px = toX(pt.median_lst_h);
                  const showTime = pt.platform === "Aqua" || pt.platform === "Terra";
                  const isDriftedYear = pt.year >= 2026;
                  return (
                    <g
                      key={pt.year}
                      onMouseEnter={() =>
                        setTooltip({
                          leftPct: (px / W) * 100,
                          topPct: (cy / H) * 100,
                          heading: `${pt.platform} · ${pt.year}`,
                          lines: [
                            `Median ${hhmm(pt.median_lst_h)} local solar time`,
                            `n = ${fmt(pt.n)} daytime detections`,
                          ],
                        })
                      }
                    >
                      {/* Continuous always-on beacon pulse ring */}
                      <circle
                        cx={px}
                        cy={cy}
                        r={6}
                        fill="none"
                        stroke={pt.colour}
                        strokeWidth={isDriftedYear ? 2 : 1.4}
                      >
                        <animate
                          attributeName="r"
                          values="6;19"
                          dur={isDriftedYear ? "2.2s" : "2.8s"}
                          begin={`${(rowIdx * 0.35 + pt.yearIdx * 0.5).toFixed(2)}s`}
                          repeatCount="indefinite"
                        />
                        <animate
                          attributeName="opacity"
                          values={isDriftedYear ? "0.78;0" : "0.45;0"}
                          dur={isDriftedYear ? "2.2s" : "2.8s"}
                          begin={`${(rowIdx * 0.35 + pt.yearIdx * 0.5).toFixed(2)}s`}
                          repeatCount="indefinite"
                        />
                      </circle>

                      <circle
                        cx={px}
                        cy={cy}
                        r={6.2}
                        fill={pt.colour}
                        stroke="#05080f"
                        strokeWidth={2}
                      />

                      {showTime && (
                        <text x={px} y={cy - 13} textAnchor="middle" className="anim-point-label">
                          {hhmm(pt.median_lst_h)}
                        </text>
                      )}

                      <circle cx={px} cy={cy} r={14} fill="transparent" />
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>

        {tooltip && (
          <div
            className="anim-tooltip"
            style={{
              left: `${Math.min(Math.max(tooltip.leftPct, 14), 86)}%`,
              top: `${Math.max(tooltip.topPct, 18)}%`,
            }}
          >
            <strong>{tooltip.heading}</strong>
            {tooltip.lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        )}
      </div>

      {children}
    </div>
  );
}

export function AnimatedIntervalChart({
  rows,
  title,
  unit,
  log,
  reference,
  intervalLabel,
  fmt,
  children,
}: {
  rows: IntervalChartRow[];
  title: string;
  unit?: string;
  log?: boolean;
  reference?: number;
  intervalLabel: string;
  fmt: (n: number, d?: number) => string;
  children?: React.ReactNode;
}) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const scale = log
    ? logScaleTicks(rows, reference)
    : (() => {
        const vals = rows.flatMap((r) => [r.value, r.lo ?? r.value, r.hi ?? r.value]);
        if (reference !== undefined) vals.push(reference);
        return niceLinearTicks(Math.min(...vals), Math.max(...vals), 6);
      })();

  const mapVal = (v: number) => (log ? Math.log10(Math.max(v, 1e-9)) : v);
  const dMin = mapVal(scale.lo);
  const dMax = mapVal(scale.hi);

  const maxLabelChars = rows.reduce((acc, r) => Math.max(acc, r.label.length), 0);
  const W = 620;
  const padL = maxLabelChars > 22 ? 235 : 158;
  const padR = 32;
  const padT = 30;
  const padB = 38;
  const rowStep = 64;
  const H = padT + Math.max(rows.length, 1) * rowStep + padB;
  const plotW = W - padL - padR;

  const toX = (v: number) => padL + ((mapVal(v) - dMin) / (dMax - dMin || 1)) * plotW;
  const toY = (idx: number) => padT + (idx + 0.52) * rowStep;

  return (
    <div className="glass-card hz-chart-card anim-chart-card">
      <div className="anim-chart-legend">
        <b className="anim-legend-title">{title}</b>
        <span>● estimate</span>
        <span>— {intervalLabel}</span>
        <span className="anim-live-pill">
          <span className="anim-live-dot" aria-hidden="true" />
          Live
        </span>
      </div>

      <div className="anim-svg-wrap" onMouseLeave={() => setTooltip(null)}>
        <svg
          className="anim-svg-chart"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Animated interval chart: ${title}`}
        >
          {/* Vertical gridlines & axis ticks */}
          {scale.ticks.map((tick) => {
            const gx = toX(tick);
            const label = log ? String(tick) : Number(tick.toFixed(3)).toString();
            return (
              <g key={tick}>
                <line x1={gx} y1={padT - 8} x2={gx} y2={H - padB + 4} className="anim-grid-line" />
                <text x={gx} y={H - 12} textAnchor="middle" className="anim-axis-text">
                  {label}
                </text>
              </g>
            );
          })}

          {/* Reference vertical benchmark line */}
          {reference !== undefined && (
            <g>
              <line
                x1={toX(reference)}
                y1={padT - 10}
                x2={toX(reference)}
                y2={H - padB + 4}
                className="anim-ref-line"
              />
              <text x={toX(reference)} y={padT - 15} textAnchor="middle" className="anim-ref-label">
                REF {reference}
              </text>
            </g>
          )}

          {/* Interval rows */}
          {rows.map((r, idx) => {
            const cy = toY(idx);
            const vx = toX(r.value);
            const hasInterval = r.lo != null && r.hi != null;
            const xLo = hasInterval ? toX(r.lo!) : vx;
            const xHi = hasInterval ? toX(r.hi!) : vx;
            const digits = r.value < 10 ? 2 : 1;
            const valLabel = fmt(r.value, digits);

            const showRowTooltip = () =>
              setTooltip({
                leftPct: (vx / W) * 100,
                topPct: (cy / H) * 100,
                heading: r.label,
                lines: [
                  `${fmt(r.value, 3)}${unit ? ` ${unit}` : ""}`,
                  ...(hasInterval ? [`${intervalLabel}: ${fmt(r.lo!, 3)} – ${fmt(r.hi!, 3)}`] : []),
                  `status: ${r.status}`,
                ],
              });

            return (
              <g
                key={r.label}
                className="anim-hit-row"
                onMouseEnter={showRowTooltip}
              >
                <rect
                  x={padL}
                  y={cy - rowStep / 2 + 4}
                  width={plotW}
                  height={rowStep - 8}
                  rx={6}
                  className="anim-row-highlight"
                />
                <line x1={padL} y1={cy} x2={W - padR} y2={cy} className="anim-row-guide" />
                <text x={padL - 12} y={cy + 4} textAnchor="end" className="anim-row-label">
                  {r.label}
                </text>

                {hasInterval && (
                  <>
                    {/* Breathing confidence glow behind interval */}
                    <line
                      x1={xLo}
                      y1={cy}
                      x2={xHi}
                      y2={cy}
                      stroke={r.colour}
                      strokeLinecap="round"
                      className="anim-ci-aura"
                      style={{ animationDelay: `${idx * 0.6}s` }}
                    />
                    {/* Crisp interval line */}
                    <line x1={xLo} y1={cy} x2={xHi} y2={cy} stroke={r.colour} strokeWidth={2.8} />
                    {/* Bracket end caps */}
                    <line x1={xLo} y1={cy - 5} x2={xLo} y2={cy + 5} stroke={r.colour} strokeWidth={2} />
                    <line x1={xHi} y1={cy - 5} x2={xHi} y2={cy + 5} stroke={r.colour} strokeWidth={2} />
                    {/* Continuously flowing shimmer stream across the CI */}
                    <line
                      x1={xLo}
                      y1={cy}
                      x2={xHi}
                      y2={cy}
                      stroke="#ffffff"
                      strokeOpacity={0.55}
                      strokeWidth={2}
                      className="anim-ci-stream"
                    />
                    {/* Oscillating confidence interval probe bead */}
                    <circle cy={cy} r={3} fill="#ffffff" fillOpacity={0.9}>
                      <animate
                        attributeName="cx"
                        values={`${xLo};${xHi};${xLo}`}
                        keyTimes="0;0.5;1"
                        calcMode="spline"
                        keySplines="0.42 0 0.58 1;0.42 0 0.58 1"
                        dur="3.6s"
                        begin={`${idx * 0.8}s`}
                        repeatCount="indefinite"
                      />
                      <animate
                        attributeName="opacity"
                        values="0.45;0.95;0.45"
                        dur="1.8s"
                        repeatCount="indefinite"
                      />
                    </circle>
                  </>
                )}

                {/* Continuous concentric sonar ring on the estimate dot */}
                <circle cx={vx} cy={cy} r={6} fill="none" stroke={r.colour} strokeWidth={2}>
                  <animate
                    attributeName="r"
                    values="6;19"
                    dur="2.3s"
                    begin={`${idx * 0.7}s`}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values="0.82;0"
                    dur="2.3s"
                    begin={`${idx * 0.7}s`}
                    repeatCount="indefinite"
                  />
                </circle>

                {/* Core estimate marker */}
                <circle cx={vx} cy={cy} r={6.2} fill={r.colour} stroke="#05080f" strokeWidth={2}>
                  <animate
                    attributeName="r"
                    values="6;7;6"
                    dur="2.3s"
                    begin={`${idx * 0.7}s`}
                    repeatCount="indefinite"
                  />
                </circle>

                {/* Crisp value label positioned cleanly above dot */}
                <text x={vx} y={cy - 14} textAnchor="middle" className="anim-point-label">
                  {valLabel}
                </text>

                {/* Wide hover hit area */}
                <rect x={Math.min(xLo, vx) - 10} y={cy - 18} width={Math.max(xHi - xLo, 20) + 20} height={36} fill="transparent" />
              </g>
            );
          })}
        </svg>

        {tooltip && (
          <div
            className="anim-tooltip"
            style={{
              left: `${Math.min(Math.max(tooltip.leftPct, 18), 82)}%`,
              top: `${Math.max(tooltip.topPct, 20)}%`,
            }}
          >
            <strong>{tooltip.heading}</strong>
            {tooltip.lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        )}
      </div>

      {children}
    </div>
  );
}

