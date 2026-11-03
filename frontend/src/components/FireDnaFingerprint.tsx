import type { FireDnaProfile } from "../types/api";

const TAU = Math.PI * 2;

function point(cx: number, cy: number, radius: number, angle: number) {
  return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
}

function segmentPath(index: number, radius: number) {
  const start = -Math.PI / 2 + (index * TAU) / 12 + 0.025;
  const end = -Math.PI / 2 + ((index + 1) * TAU) / 12 - 0.025;
  const inner = 31;
  const [a, b, c, d] = [
    point(100, 100, inner, start),
    point(100, 100, radius, start),
    point(100, 100, radius, end),
    point(100, 100, inner, end),
  ];
  return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]} A ${radius} ${radius} 0 0 1 ${c[0]} ${c[1]} L ${d[0]} ${d[1]} A ${inner} ${inner} 0 0 0 ${a[0]} ${a[1]} Z`;
}

export default function FireDnaFingerprint({ profile }: { profile: FireDnaProfile }) {
  const values = profile.monthly_reference.map((row) => row.median_activity ?? 0);
  const max = Math.max(...values, 1);

  return (
    <figure className="dna-fingerprint w-full flex flex-col items-center justify-center m-0" aria-labelledby="dna-fingerprint-title">
      <svg viewBox="0 0 200 200" className="w-52 h-52 overflow-visible" role="img" aria-label="Circular twelve-month seasonal activity fingerprint">
        {profile.monthly_reference.map((row, index) => {
          const ratio = (row.median_activity ?? 0) / max;
          const radius = 43 + ratio * 43;
          const color =
            ratio > 0.75 ? "#f97316" : ratio > 0.45 ? "#fbbf24" : ratio > 0.2 ? "#38bdf8" : "#0284c7";
          const label = point(100, 100, 95, -Math.PI / 2 + ((index + 0.5) * TAU) / 12);
          return (
            <g key={row.name}>
              <path
                d={segmentPath(index, radius)}
                fill={color}
                stroke="#090e1a"
                strokeWidth="1.5"
                opacity={ratio > 0.1 ? 0.95 : 0.4}
              >
                <title>
                  {row.name}: typical activity {row.median_activity?.toFixed(1) ?? "no data"}
                </title>
              </path>
              <text
                x={label[0]}
                y={label[1]}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#94a3b8"
                fontSize="8"
                fontWeight="600"
              >
                {row.name}
              </text>
            </g>
          );
        })}
        <circle cx="100" cy="100" r="27" fill="#090e1a" stroke="#38bdf8" strokeWidth="2" />
        <text className="dna-center" x="100" y="96" textAnchor="middle" fill="#ffffff" fontSize="9" fontWeight="900">
          FIRE
        </text>
        <text className="dna-center" x="100" y="108" textAnchor="middle" fill="#38bdf8" fontSize="9" fontWeight="900">
          DNA
        </text>
      </svg>
      <div className="flex items-center gap-2 mt-4 text-[11px] font-semibold text-slate-400">
        <span>Low Baseline</span>
        <div className="flex items-center gap-1">
          <span className="w-3 h-2 rounded-xs bg-sky-700" />
          <span className="w-3 h-2 rounded-xs bg-sky-400" />
          <span className="w-3 h-2 rounded-xs bg-amber-400" />
          <span className="w-3 h-2 rounded-xs bg-orange-500" />
        </div>
        <span>Peak Radiance</span>
      </div>
    </figure>
  );
}
