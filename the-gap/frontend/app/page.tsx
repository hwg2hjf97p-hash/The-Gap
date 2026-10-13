import { Logo } from "../components/Logo";

// The public site is deliberately bare: the logo, a contact email and the legal pages.
export default function Home() {
  return (
    <div className="mx-auto max-w-xl px-5 flex flex-col items-center text-center" style={{ minHeight: "60vh", justifyContent: "center", paddingTop: "12vh", paddingBottom: "8vh" }}>
      <Logo size={96} />
      <h1 className="mt-6 text-3xl font-bold tracking-tight" style={{ color: "#f2f6f8" }}>
        The Gap
      </h1>
      <p className="mt-6 text-sm">
        <a href="mailto:hello@causalme.com" style={{ color: "#22d3ee" }}>
          hello@causalme.com
        </a>
      </p>
      <p className="mt-4 flex gap-6 text-sm" style={{ color: "#9aa8b2" }}>
        <a href="/privacy" className="hover:text-white transition-colors">
          Privacy Policy
        </a>
        <a href="/terms" className="hover:text-white transition-colors">
          Terms of Service
        </a>
      </p>
    </div>
  );
}
