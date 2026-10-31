import type { FireDnaProfile } from "../types/api";

const TAU = Math.PI * 2;
function point(cx: number, cy: number, radius: number, angle: number) {
  return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
}
function segmentPath(index: number, radius: number) {
  const start = -Math.PI / 2 + index * TAU / 12 + 0.025;
  const end = -Math.PI / 2 + (index + 1) * TAU / 12 - 0.025;
  const inner = 31;
  const [a, b, c, d] = [point(100, 100, inner, start), point(100, 100, radius, start), point(100, 100, radius, end), point(100, 100, inner, end)];
  return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]} A ${radius} ${radius} 0 0 1 ${c[0]} ${c[1]} L ${d[0]} ${d[1]} A ${inner} ${inner} 0 0 0 ${a[0]} ${a[1]} Z`;
}

export default function FireDnaFingerprint({ profile }: { profile: FireDnaProfile }) {
  const values = profile.monthly_reference.map((row) => row.median_activity ?? 0);
  const max = Math.max(...values, 1);
  return <figure className="dna-fingerprint" aria-labelledby="dna-fingerprint-title">
    <figcaption id="dna-fingerprint-title"><b>4.</b><span><strong>Fire DNA Fingerprint</strong><small>Multi-dimensional seasonal signature</small></span></figcaption>
    <svg viewBox="0 0 200 200" role="img" aria-label="Circular twelve-month seasonal activity fingerprint">
      {profile.monthly_reference.map((row, index) => {
        const ratio = (row.median_activity ?? 0) / max;
        const radius = 43 + ratio * 43;
        const color = ratio > .75 ? "#ff5b35" : ratio > .45 ? "#ff9f43" : ratio > .2 ? "#36c9df" : "#17607c";
        const label = point(100, 100, 95, -Math.PI / 2 + (index + .5) * TAU / 12);
        return <g key={row.name}>
          <path d={segmentPath(index, radius)} fill={color} stroke="#071522" strokeWidth="1.2"><title>{row.name}: typical activity {row.median_activity?.toFixed(1) ?? "no data"}</title></path>
          <text x={label[0]} y={label[1]} textAnchor="middle" dominantBaseline="middle">{row.name}</text>
        </g>;
      })}
      <circle cx="100" cy="100" r="27" fill="#071421" stroke="#52d6f7" strokeWidth="1.5" />
      <text className="dna-center" x="100" y="96" textAnchor="middle">FIRE</text><text className="dna-center" x="100" y="108" textAnchor="middle">DNA</text>
    </svg>
    <div className="dna-scale"><span>Lower activity</span><i /><i /><i /><i /><span>Higher activity</span></div>
  </figure>;
}
