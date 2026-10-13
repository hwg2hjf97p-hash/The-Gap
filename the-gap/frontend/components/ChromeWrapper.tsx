import type { ReactNode } from "react";
import { Logo } from "./Logo";

/** The site frame: a slim top bar with the logo, and a footer with the contact email and legal pages. */
export default function ChromeWrapper({ children }: { children: ReactNode }) {
  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md"
        style={{ background: "rgba(11,16,21,0.72)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <nav className="mx-auto max-w-5xl flex items-center px-5 py-3">
          <a href="/" className="flex items-center gap-2.5" aria-label="The Gap home">
            <Logo size={30} />
            <span className="text-lg font-semibold tracking-tight" style={{ color: "#f2f6f8" }}>
              The Gap
            </span>
          </a>
        </nav>
      </header>

      <main className="pt-14">{children}</main>

      <footer className="mt-24 px-5 pb-12" style={{ color: "#9aa8b2" }}>
        <div className="mx-auto max-w-5xl pt-8 text-xs leading-relaxed" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>
              © 2026 The Gap ·{" "}
              <a href="mailto:hello@causalme.com" style={{ color: "#22d3ee" }}>
                hello@causalme.com
              </a>
            </p>
            <p className="flex gap-4">
              <a href="/privacy" className="hover:text-white">
                Privacy Policy
              </a>
              <a href="/terms" className="hover:text-white">
                Terms of Service
              </a>
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}
