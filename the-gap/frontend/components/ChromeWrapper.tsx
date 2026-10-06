import type { ReactNode } from "react";
import { Logo } from "./Logo";

/** The site frame: a slim top bar and a footer. The site is information only, with no app to use here. */
export default function ChromeWrapper({ children }: { children: ReactNode }) {
  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md"
        style={{ background: "rgba(11,16,21,0.72)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <nav className="mx-auto max-w-5xl flex items-center justify-between px-5 py-3">
          <a href="/" className="flex items-center gap-2.5" aria-label="The Gap home">
            <Logo size={30} />
            <span className="text-lg font-semibold tracking-tight" style={{ color: "#f2f6f8" }}>
              The Gap
            </span>
          </a>
          <div className="flex items-center gap-5 text-sm" style={{ color: "#9aa8b2" }}>
            <a href="/privacy" className="hidden sm:inline hover:text-white transition-colors">
              Privacy
            </a>
            <a href="/terms" className="hidden sm:inline hover:text-white transition-colors">
              Terms
            </a>
            <a
              href="mailto:hello@causalme.com?subject=Early%20access%20to%20The%20Gap"
              className="rounded-full px-4 py-1.5 font-semibold transition-opacity hover:opacity-90"
              style={{ background: "#22d3ee", color: "#04141a" }}
            >
              Early access
            </a>
          </div>
        </nav>
      </header>

      <main className="pt-14">{children}</main>

      <footer className="mt-24 px-5 pb-12" style={{ color: "#9aa8b2" }}>
        <div className="mx-auto max-w-5xl pt-8 text-xs leading-relaxed" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>
              © 2026 The Gap · Samuel Roberts, Queensland, Australia ·{" "}
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
          <p className="mt-4 opacity-70">
            The Gap provides general information about your own data. It is not medical advice and does not diagnose, treat or prevent any condition. Apple, Apple Health, Apple Watch,
            Whoop, Oura, Strava, Withings, Polar and Google are trademarks of their respective owners. The Gap is not affiliated with or endorsed by them.
          </p>
        </div>
      </footer>
    </>
  );
}
