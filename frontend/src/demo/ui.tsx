import type { CSSProperties, ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { NOW_LABEL } from "./data";

export const C = { obs: "var(--obs)", inf: "var(--inf)", ext: "var(--ext)", fc: "var(--fc)", red: "var(--red)", yellow: "var(--yellow)" };

type Screen = { to: string; label: string };
type Section = { to: string; label: string; n?: string; screens?: Screen[] };

export const SECTIONS: Section[] = [
  { to: "/", label: "Overview" },
  { to: "/fire-memory", label: "Fire Memory", n: "01", screens: [{ to: "/fire-memory", label: "Burning calendar" }, { to: "/fire-memory/anomaly", label: "Current vs. historical" }] },
  { to: "/fire-now", label: "Fire Now", n: "02", screens: [{ to: "/fire-now", label: "3D globe" }, { to: "/fire-now/area", label: "Area of interest" }, { to: "/fire-now/quality", label: "Observation quality" }] },
  { to: "/fire-identity", label: "Fire Identity", n: "03" },
  { to: "/fire-evidence", label: "Fire Evidence", n: "04", screens: [{ to: "/fire-evidence", label: "Independent sources" }, { to: "/fire-evidence/news", label: "Local news & NLP" }, { to: "/fire-evidence/fusion", label: "Fusion & validation" }, { to: "/fire-evidence/case", label: "Fire case" }] },
  { to: "/fire-past", label: "Fire Past", n: "05" },
  { to: "/fire-future", label: "Fire Future", n: "06" },
  { to: "/exposure", label: "Exposure", n: "07" },
  { to: "/methods", label: "Data & Methods", screens: [{ to: "/methods", label: "Full workflow" }, { to: "/methods/harmonization", label: "Sensor harmonization" }] },
];

export function Shell() {
  const { pathname } = useLocation();
  const section = SECTIONS.find((s) => (s.to === "/" ? pathname === "/" : pathname.startsWith(s.to)));
  return (
    <div className="fs-app">
      <header className="fs-header">
        <NavLink to="/" className="fs-brand">
          <img className="fs-brand-logo" src="/logo.png" alt="FlameSeek logo" />
          <span><b>FlameSeek</b><small>FIRE INTELLIGENCE PLATFORM</small></span>
        </NavLink>
        <nav className="fs-nav">
          {SECTIONS.map((s) => (
            <NavLink key={s.to} to={s.to} className={section === s ? "active" : ""}>{s.n && <i>{s.n}</i>}{s.label}</NavLink>
          ))}
        </nav>
        <div className="fs-header-right">
          <span className="fs-demo-chip">Illustrative data</span>
          <span className="fs-nrt">NRT</span>
          <span>{NOW_LABEL}</span>
        </div>
      </header>
      {section?.screens && (
        <div className="fs-subnav">
          <span>{section.label}</span>
          {section.screens.map((s) => <NavLink key={s.to} to={s.to} end>{s.label}</NavLink>)}
        </div>
      )}
      <main className="fs-main"><Outlet /></main>
      <footer className="fs-footer">
        <span style={{ "--c": C.obs } as CSSProperties}>Observation: what satellites detected</span>
        <span style={{ "--c": C.inf } as CSSProperties}>Inference: what FlameSeek concludes</span>
        <span style={{ "--c": C.ext } as CSSProperties}>External evidence: independent sources</span>
        <span style={{ "--c": C.fc } as CSSProperties}>Forecast: next valid observation window</span>
        <em>Illustrative data modelled on NASA FIRMS (MODIS C6.1, VIIRS 375 m) · Basemap: Natural Earth</em>
      </footer>
    </div>
  );
}

export function PageHead({ eyebrow, title, sub, right }: { eyebrow: string; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="fs-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {right && <div className="fs-head-right">{right}</div>}
    </div>
  );
}

type CardProps = { title?: ReactNode; n?: string; meta?: ReactNode; accent?: string; top?: string; glass?: boolean; className?: string; style?: CSSProperties; children?: ReactNode };

export function Card({ title, n, meta, accent, top, glass, className = "", style, children }: CardProps) {
  const cls = ["card", accent ? "acc" : "", top ? "top" : "", glass ? "glass" : "", className].filter(Boolean).join(" ");
  return (
    <section className={cls} style={{ ...(accent || top ? ({ "--c": accent ?? top } as CSSProperties) : {}), ...style }}>
      {title && <div className="card-h">{n && <b>{n}</b>}<span>{title}</span>{meta && <small>{meta}</small>}</div>}
      {children}
    </section>
  );
}

export function KV({ k, v, color }: { k: ReactNode; v: ReactNode; color?: string }) {
  return <div className="kv"><span>{k}</span><b style={color ? { color } : undefined}>{v}</b></div>;
}

export function Chip({ tone, sm, children }: { tone?: string; sm?: boolean; children: ReactNode }) {
  return <span className={`chip${tone ? " t" : ""}${sm ? " sm" : ""}`} style={tone ? ({ "--c": tone } as CSSProperties) : undefined}>{children}</span>;
}

export function Seg({ options, value, onChange }: { options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="seg">
      {options.map((o) => <button key={o} type="button" className={o === value ? "on" : ""} onClick={() => onChange(o)}>{o}</button>)}
    </div>
  );
}

export function Bar({ value, color }: { value: number; color?: string }) {
  return <span className="bar" style={color ? ({ "--c": color } as CSSProperties) : undefined}><i style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></span>;
}

export function Legend({ items }: { items: Array<[string, string]> }) {
  return <div className="legend">{items.map(([label, color]) => <span key={label}><i style={{ "--c": color } as CSSProperties} />{label}</span>)}</div>;
}

// --- tiny SVG helpers ---------------------------------------------------------------------------

export const lin = (d0: number, d1: number, r0: number, r1: number) => (v: number) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

export const path = (pts: Array<[number, number]>) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

export function smooth(pts: Array<[number, number]>) {
  if (pts.length < 3) return path(pts);
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    d += ` C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)},${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)},${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

export function Chart({ w = 600, h = 260, children, style }: { w?: number; h?: number; children: ReactNode; style?: CSSProperties }) {
  return <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "100%", minHeight: 0, flex: 1, ...style }}>{children}</svg>;
}

export function YGrid({ ticks, y, x0, x1, fmt = (v) => String(v) }: { ticks: number[]; y: (v: number) => number; x0: number; x1: number; fmt?: (v: number) => string }) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x0} x2={x1} y1={y(t)} y2={y(t)} stroke="#17233a" />
          <text x={x0 - 6} y={y(t) + 3} textAnchor="end" className="ax">{fmt(t)}</text>
        </g>
      ))}
    </g>
  );
}
