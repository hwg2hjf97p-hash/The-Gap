export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-5 py-32 text-center">
      <p className="text-[11px] font-bold tracking-[0.22em]" style={{ color: "#22d3ee" }}>
        404
      </p>
      <h1 className="mt-3 text-3xl font-bold" style={{ color: "#f2f6f8" }}>
        That page isn&apos;t here
      </h1>
      <p className="mt-3 text-sm" style={{ color: "#9aa8b2" }}>
        The link may be old or mistyped.
      </p>
      <a href="/" className="mt-8 inline-block rounded-full px-6 py-3 text-sm font-bold" style={{ background: "#22d3ee", color: "#04141a" }}>
        Go to the home page
      </a>
    </div>
  );
}
