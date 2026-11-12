export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-5 py-32 text-center">
      <p className="text-[11px] font-bold tracking-[0.22em]" style={{ color: "#e0a458" }}>
        404
      </p>
      <h1 className="mt-3 text-3xl font-bold" style={{ color: "#f1ebe2" }}>
        That page isn&apos;t here
      </h1>
      <p className="mt-3 text-sm" style={{ color: "#a0968a" }}>
        The link may be old or mistyped.
      </p>
      <a href="/" className="mt-8 inline-block rounded-full px-6 py-3 text-sm font-bold" style={{ background: "#e0a458", color: "#1a1208" }}>
        Go to the home page
      </a>
    </div>
  );
}
