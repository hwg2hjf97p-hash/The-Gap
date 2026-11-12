import type { ReactNode } from "react";
import { APP_LIVE, SITE } from "../../lib/site";

/** Page-wide building blocks for the public pages, in the site's existing dark look. */

export function JsonLd({ data }: { data: object }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }} />;
}

export function Wrap({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return <div className={`mx-auto px-5 ${narrow ? "max-w-2xl" : "max-w-5xl"}`}>{children}</div>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold tracking-widest uppercase" style={{ color: "#e0a458" }}>
      {children}
    </p>
  );
}

export function H1({ children }: { children: ReactNode }) {
  return (
    <h1 className="mt-3 text-3xl sm:text-5xl font-bold tracking-tight leading-tight" style={{ color: "#f1ebe2" }}>
      {children}
    </h1>
  );
}

export function H2({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="mt-12 mb-3 text-2xl font-bold tracking-tight" style={{ color: "#f1ebe2" }}>
      {children}
    </h2>
  );
}

export function H3({ children }: { children: ReactNode }) {
  return (
    <h3 className="mt-6 mb-2 text-lg font-semibold" style={{ color: "#f1ebe2" }}>
      {children}
    </h3>
  );
}

export function P({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return (
    <p className="mt-3 text-base leading-relaxed" style={{ color: muted ? "#a0968a" : "#d8d0c4" }}>
      {children}
    </p>
  );
}

export function UL({ items }: { items: ReactNode[] }) {
  return (
    <ul className="mt-3 space-y-2 pl-5 list-disc text-base leading-relaxed" style={{ color: "#d8d0c4" }}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl p-5" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}>
      {title && (
        <h3 className="text-base font-semibold mb-1.5" style={{ color: "#f1ebe2" }}>
          {title}
        </h3>
      )}
      <div className="text-sm leading-relaxed" style={{ color: "#cbc2b5" }}>
        {children}
      </div>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 rounded-xl p-4 text-sm leading-relaxed" style={{ background: "rgba(224,164,88,0.08)", border: "1px solid rgba(224,164,88,0.28)", color: "#d8d0c4" }}>
      {children}
    </div>
  );
}

/** The one call to action. Before launch it says so and offers an email; on launch day (APP_LIVE) it becomes the App Store link. */
export function GetTheApp({ compact = false }: { compact?: boolean }) {
  if (APP_LIVE) {
    return (
      <div className={compact ? "mt-4" : "mt-8"}>
        <a
          href={SITE.appStoreUrl}
          className="inline-block rounded-xl px-6 py-3 text-base font-semibold"
          style={{ background: "#e0a458", color: "#1a1208" }}
        >
          Download on the App Store
        </a>
        <p className="mt-3 text-sm" style={{ color: "#a0968a" }}>
          Free to download. First month free, then {SITE.priceMonthly} a month or {SITE.priceYearly} a year. Cancel any time.
        </p>
      </div>
    );
  }
  return (
    <div className={compact ? "mt-4" : "mt-8"}>
      <p className="inline-block rounded-xl px-5 py-3 text-base font-semibold" style={{ background: "rgba(224,164,88,0.12)", border: "1px solid rgba(224,164,88,0.4)", color: "#e0a458" }}>
        Launching on the iPhone App Store soon
      </p>
      <p className="mt-3 text-sm" style={{ color: "#a0968a" }}>
        Want to hear the moment it's live?{" "}
        <a href={`mailto:${SITE.email}?subject=Tell%20me%20when%20The%20Gap%20is%20live`} style={{ color: "#e0a458", textDecoration: "underline" }}>
          Email {SITE.email}
        </a>
        .
      </p>
    </div>
  );
}

export function Breadcrumb({ items }: { items: { name: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs" style={{ color: "#a0968a" }}>
      {items.map((item, i) => (
        <span key={item.name}>
          {item.href ? (
            <a href={item.href} className="hover:text-white" style={{ textDecoration: "underline" }}>
              {item.name}
            </a>
          ) : (
            item.name
          )}
          {i < items.length - 1 ? " / " : ""}
        </span>
      ))}
    </nav>
  );
}
