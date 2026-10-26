/**
 * The fixed backdrop behind every page, the same look as the app: a near-black base with a teal glow fading in from the top (and more
 * faintly the bottom) and the logo mark very faintly in the centre. It stays still while the page scrolls over it. Decorative only.
 */
export default function SiteBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 95% 42% at 50% 0%, rgba(20,184,198,0.5), rgba(20,184,198,0) 100%), radial-gradient(ellipse 85% 26% at 50% 100%, rgba(20,184,198,0.2), rgba(20,184,198,0) 100%)",
        }}
      />
      <div className="absolute inset-0 flex items-center justify-center">
        <svg viewBox="0 0 1024 1024" style={{ width: "min(78vmin, 820px)", height: "min(78vmin, 820px)", opacity: 0.06 }}>
          <path d="M 772.8 442.1 A 270 270 0 1 1 581.9 251.2" fill="none" stroke="#ffffff" strokeWidth="76" strokeLinecap="round" />
          <circle cx="702.9" cy="321.1" r="42" fill="#ffffff" />
        </svg>
      </div>
    </div>
  );
}
