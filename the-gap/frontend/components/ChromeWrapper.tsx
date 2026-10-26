import type { ReactNode } from "react";
import { Logo } from "./Logo";

const NAV = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/faq", label: "FAQ" },
  { href: "/compare", label: "Compare" },
  { href: "/guides", label: "Guides" },
];

/** The site frame: a slim top bar with the logo and main pages, and a footer with the contact email and legal pages. */
export default function ChromeWrapper({ children }: { children: ReactNode }) {
  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md"
        style={{ background: "rgba(11,16,21,0.72)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <nav className="mx-auto max-w-5xl flex items-center justify-between gap-4 px-5 py-3" aria-label="Main">
          <a href="/" className="flex items-center gap-2.5 shrink-0" aria-label="The Gap home">
            <Logo size={30} />
            <span className="text-lg font-semibold tracking-tight" style={{ color: "#f2f6f8" }}>
              The Gap
            </span>
          </a>
          <ul className="hidden sm:flex items-center gap-5 text-sm" style={{ color: "#9aa8b2" }}>
            {NAV.map((n) => (
              <li key={n.href}>
                <a href={n.href} className="hover:text-white transition-colors">
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="pt-14">{children}</main>

      <footer className="mt-24 px-5 pb-12" style={{ color: "#9aa8b2" }}>
        <div className="mx-auto max-w-5xl pt-8 text-xs leading-relaxed" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <ul className="flex flex-wrap gap-x-5 gap-y-2 mb-4 sm:hidden">
            {NAV.map((n) => (
              <li key={n.href}>
                <a href={n.href} className="hover:text-white">
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>
              © 2026 The Gap app by CausalMe ·{" "}
              <a href="mailto:hello@causalme.com" style={{ color: "#22d3ee" }}>
                hello@causalme.com
              </a>
            </p>
            <p className="flex flex-wrap gap-4">
              <a href="/press" className="hover:text-white">
                Press
              </a>
              <a href="/privacy" className="hover:text-white">
                Privacy Policy
              </a>
              <a href="/terms" className="hover:text-white">
                Terms of Service
              </a>
            </p>
          </div>
          <p className="mt-4">General information, not medical advice.</p>
        </div>
      </footer>
    </>
  );
}
