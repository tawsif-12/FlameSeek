import type { CSSProperties, ReactNode } from "react";
import { BD_CITIES, BD_OUTLINE, BD_RIVERS } from "./data";

// Schematic maps for the demo. Shapes are approximate and hand-drawn, not survey data.

export const BD_W = 1000;
export const BD_H = 720;
export const bdProject = (lon: number, lat: number): [number, number] => [(lon - 84.5) * 90.9, (27.3 - lat) * 98.6];
const pts = (coords: Array<[number, number]>) => coords.map(([lon, lat]) => bdProject(lon, lat).map((v) => v.toFixed(1)).join(",")).join(" ");

export function BdMap({ children, cities = true, fill = "#13203a" }: { children?: ReactNode; cities?: boolean; fill?: string }) {
  const lons = Array.from({ length: 11 }, (_, i) => 85 + i);
  const lats = Array.from({ length: 8 }, (_, i) => 20 + i);
  return (
    <svg className="bg" viewBox={`0 0 ${BD_W} ${BD_H}`} preserveAspectRatio="xMidYMid meet">
      {lons.map((lon) => <line key={lon} x1={bdProject(lon, 0)[0]} x2={bdProject(lon, 0)[0]} y1={-400} y2={BD_H + 400} stroke="#0e1727" />)}
      {lats.map((lat) => <line key={lat} y1={bdProject(0, lat)[1]} y2={bdProject(0, lat)[1]} x1={-800} x2={BD_W + 800} stroke="#0e1727" />)}
      {BD_RIVERS.map((r, i) => <polyline key={i} points={pts(r)} fill="none" stroke="#1d3a66" strokeWidth={i === 0 ? 2 : 1.3} strokeLinejoin="round" opacity={0.45} />)}
      <polygon points={pts(BD_OUTLINE)} fill={fill} stroke="#2b4670" strokeWidth={1.2} strokeLinejoin="round" />
      {BD_RIVERS.map((r, i) => <polyline key={i} points={pts(r)} fill="none" stroke="#1d3a66" strokeWidth={1} strokeLinejoin="round" opacity={0.5} />)}
      {children}
      {cities && BD_CITIES.map(([name, lon, lat]) => {
        const [x, y] = bdProject(lon, lat);
        return <g key={name}><circle cx={x} cy={y} r={2} fill="#dbe5f5" /><text x={x + 5} y={y + 3} className="map-label">{name}</text></g>;
      })}
    </svg>
  );
}

// Local map around the demo event (east Sundarbans). 1000 × 600 canvas; the event sits at (430, 400).
export const EVT: [number, number] = [430, 400];

type LocalMapProps = { children?: ReactNode; viewBox?: string; className?: string; style?: CSSProperties; fit?: "slice" | "meet"; label?: boolean };

export function LocalMap({ children, viewBox = "0 0 1000 600", className, style, fit = "slice", label = true }: LocalMapProps) {
  return (
    <svg className={className} style={style} viewBox={viewBox} preserveAspectRatio={`xMidYMid ${fit}`}>
      <rect x={-600} y={-400} width={2200} height={1400} fill="#0a1220" />
      <polygon points="-600,-400 548,-400 540,0 520,120 500,220 520,330 560,430 600,520 620,600 640,1000 -600,1000" fill="#131f38" />
      <path d="M-600,120 C-300,150 -100,150 0,140 C120,110 260,150 380,210 C440,240 480,300 520,330 L560,430 L600,520 L620,600 L640,1000 L-600,1000 Z" fill="#14302f" />
      <polygon points="604,-400 1600,-400 1600,1000 720,1000 690,600 670,520 640,430 600,330 580,220 590,120 600,0" fill="#131f38" />
      <polygon points="760,-400 800,-100 770,80 800,240 860,380 900,600 930,1000 990,1000 950,600 920,380 850,230 830,80 850,-100 830,-400" fill="#0a1220" opacity={0.9} />
      <path d="M150,1000 C160,700 120,380 180,250 C200,200 170,170 160,140" fill="none" stroke="#0a1220" strokeWidth={9} />
      <path d="M330,1000 C350,640 300,420 360,330 C390,280 370,240 380,210" fill="none" stroke="#0a1220" strokeWidth={7} />
      <path d="M-100,330 C0,340 80,300 180,250" fill="none" stroke="#0a1220" strokeWidth={5} />
      <path d="M360,330 C420,310 470,330 520,330" fill="none" stroke="#0a1220" strokeWidth={4} />
      {label && <g><circle cx={372} cy={128} r={2.2} fill="#dbe5f5" /><text x={379} y={131.5} className="map-label">Rayenda (Sharankhola)</text></g>}
      {children}
    </svg>
  );
}

// Teardrop probability corridor stretching north-east of the event.
export function Corridor({ bands = 3, scale = 1, labels = false }: { bands?: number; scale?: number; labels?: boolean }) {
  const drop = (l: number, w: number) => `M0,14 C${-w},14 ${-w * 1.05},${-l * 0.82} 0,${-l} C${w * 1.05},${-l * 0.82} ${w},14 0,14 Z`;
  const shapes: Array<[number, number, CSSProperties]> = [
    [250, 170, { fill: "rgba(167,139,250,0.12)", stroke: "rgba(221,214,254,0.75)", strokeDasharray: "5 4" }],
    [195, 122, { fill: "rgba(167,139,250,0.22)", stroke: "rgba(221,214,254,0.6)" }],
    [140, 82, { fill: "rgba(139,92,246,0.75)", stroke: "rgba(237,233,254,0.85)" }],
  ];
  return (
    <g transform={`translate(${EVT[0]},${EVT[1]}) rotate(32) scale(${scale})`}>
      {shapes.slice(3 - bands).map(([l, w, s], i) => <path key={i} d={drop(l, w)} style={s} strokeWidth={1.3} />)}
      {labels && <text x={0} y={-212} textAnchor="middle" className="map-label" transform="rotate(-32 0 -212)">24 h activity corridor</text>}
    </g>
  );
}

export function EventDot({ r = 34, label = "current event" }: { r?: number; label?: string | null }) {
  return (
    <g>
      <circle cx={EVT[0]} cy={EVT[1]} r={r} fill="rgba(239,83,80,0.72)" stroke="#fda4a4" strokeWidth={1.4} />
      {label && <text x={EVT[0] + r * 0.55} y={EVT[1] + r * 0.55} className="map-label">{label}</text>}
    </g>
  );
}
