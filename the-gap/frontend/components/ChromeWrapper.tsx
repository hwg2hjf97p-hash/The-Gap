"use client";

import { usePathname } from "next/navigation";
import BottomNav from "./BottomNav";

const APP_SHELL_PREFIXES = ["/results/live", "/journal", "/insights", "/assistant", "/settings"];

export default function ChromeWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAppShell = APP_SHELL_PREFIXES.some(
    (p) => pathname === p || pathname?.startsWith(p + "/") || pathname?.startsWith(p + "?")
  );

  if (isAppShell) {
    return (
      <>
        <main className="pb-24">{children}</main>
        <BottomNav />
      </>
    );
  }

  return (
    <>
      {/* Top nav bar */}
      <nav
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
        style={{ background: "linear-gradient(to bottom, rgba(10,23,16,0.95), transparent)" }}
      >
        <a href="/" className="flex items-center gap-2">
          <span className="text-xl font-semibold tracking-tight" style={{ color: "#eef3f0" }}>
            The Gap
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-mono"
            style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}
          >
            beta
          </span>
        </a>
        <a
          href="https://www.causalme.com"
          className="text-sm font-medium transition-colors"
          style={{ color: "#a2bcaf" }}
        >
          causalme.com
        </a>
      </nav>

      <main className="pt-16">{children}</main>

      {/* Footer */}
      <footer className="mt-24 pb-12 text-center" style={{ color: "#a2bcaf", fontSize: "0.75rem" }}>
        <p>
          © 2026 The Gap · Samuel Roberts ·{" "}
          <a href="mailto:hello@causalme.com" className="hover:text-text transition-colors" style={{ color: "#c9a84c" }}>
            hello@causalme.com
          </a>
        </p>
        <p className="mt-1 opacity-60">Causal inference powered by EconML (Microsoft Research)</p>
      </footer>
    </>
  );
}
