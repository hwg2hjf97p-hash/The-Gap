/**
 * The Gap's placeholder mark: a ring with a gap in it and a dot sitting in the
 * gap. Same geometry as the app's icon.
 */
export function Logo({ size = 48, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 1024 1024" className={className} role="img" aria-label="The Gap logo">
      <defs>
        <linearGradient id="gapRing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset="1" stopColor="#3b82f6" />
        </linearGradient>
      </defs>
      <path d="M 772.8 442.1 A 270 270 0 1 1 581.9 251.2" fill="none" stroke="url(#gapRing)" strokeWidth="76" strokeLinecap="round" />
      <circle cx="702.9" cy="321.1" r="42" fill="#34e07a" />
    </svg>
  );
}
