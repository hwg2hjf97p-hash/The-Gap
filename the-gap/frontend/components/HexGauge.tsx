/**
 * A hexagonal gauge like the ones on the app's home screen: the outline is the
 * track, and it fills clockwise from the top as `progress` (0-1) rises.
 */
export function HexGauge({
  size = 96,
  progress,
  value,
  unit,
  label,
  color,
}: {
  size?: number;
  progress: number;
  value: string;
  unit?: string;
  label: string;
  color: string;
}) {
  const stroke = 5;
  const r = (size - stroke) / 2; // circumradius of a pointy-top hexagon
  const width = Math.sqrt(3) * r + stroke;
  const cx = width / 2;
  const cy = size / 2;
  const points = [-90, -30, 30, 90, 150, 210].map((deg) => {
    const a = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
  const d = `M ${points[0][0]} ${points[0][1]} ` + points.slice(1).map((p) => `L ${p[0]} ${p[1]}`).join(" ") + " Z";
  const p = Math.max(0, Math.min(1, progress));

  return (
    <div className="flex flex-col items-center">
      <svg width={width} height={size} viewBox={`0 0 ${width} ${size}`} role="img" aria-label={`${label}: ${value} ${unit ?? ""}`.trim()}>
        <path d={d} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={stroke} strokeLinejoin="round" />
        <path d={d} fill="none" stroke={color} strokeWidth={stroke} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray={`${p} 1`} />
        <text x={cx} y={unit ? cy - 3 : cy} textAnchor="middle" dominantBaseline="central" fill="#f2f6f8" fontSize={size * 0.26} fontWeight={700}>
          {value}
        </text>
        {unit && (
          <text x={cx} y={cy + size * 0.17} textAnchor="middle" dominantBaseline="central" fill="#9aa8b2" fontSize={size * 0.11}>
            {unit}
          </text>
        )}
      </svg>
      <span className="mt-1.5 text-[11px] font-semibold" style={{ color: "#9aa8b2" }}>
        {label}
      </span>
    </div>
  );
}
