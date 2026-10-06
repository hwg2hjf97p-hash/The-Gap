import type { ReactNode } from "react";

export type LegalSection = {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
  // Shown after the bullets, e.g. a closing sentence.
  after?: string[];
  // A small table of label / description rows (used for service providers).
  rows?: { label: string; text: string }[];
};

/** One shared layout for the privacy policy and the terms, in the site's existing look. */
export default function LegalPage({
  title,
  updated,
  intro,
  sections,
  footer,
}: {
  title: string;
  updated: string;
  intro?: string[];
  sections: LegalSection[];
  footer?: ReactNode;
}) {
  return (
    <div className="min-h-screen px-5 py-16" style={{ background: "#0b1015" }}>
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2" style={{ color: "#f2f6f8" }}>
          {title}
        </h1>
        <p className="text-sm mb-8" style={{ color: "#9aa8b2" }}>
          Last updated: {updated}
        </p>

        {intro?.map((p) => (
          <p key={p} className="text-sm leading-relaxed mb-4" style={{ color: "#d3dde3" }}>
            {p}
          </p>
        ))}

        <div className="space-y-8 mt-8" style={{ color: "#d3dde3" }}>
          {sections.map((s, i) => (
            <section key={s.heading}>
              <h2 className="text-lg font-semibold mb-2" style={{ color: "#22d3ee" }}>
                {i + 1}. {s.heading}
              </h2>
              {s.paragraphs?.map((p) => (
                <p key={p} className="text-sm leading-relaxed mb-3">
                  {p}
                </p>
              ))}
              {s.bullets && (
                <ul className="text-sm leading-relaxed list-disc pl-5 space-y-1.5 mb-3">
                  {s.bullets.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              )}
              {s.rows && (
                <div className="text-sm leading-relaxed space-y-2 mb-3">
                  {s.rows.map((r) => (
                    <p key={r.label}>
                      <span style={{ color: "#f2f6f8", fontWeight: 600 }}>{r.label}.</span> {r.text}
                    </p>
                  ))}
                </div>
              )}
              {s.after?.map((p) => (
                <p key={p} className="text-sm leading-relaxed mb-3">
                  {p}
                </p>
              ))}
            </section>
          ))}
        </div>

        {footer && <div className="mt-12 text-sm" style={{ color: "#9aa8b2" }}>{footer}</div>}
      </div>
    </div>
  );
}
