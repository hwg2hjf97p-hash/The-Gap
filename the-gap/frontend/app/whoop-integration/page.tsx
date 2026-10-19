import type { Metadata } from "next";

// A page for WHOOP's app review. It is not meant to be found through search.
export const metadata: Metadata = {
  title: "The Gap: WHOOP integration",
  description: "How The Gap uses a member's own WHOOP data, with screenshots.",
  robots: { index: false, follow: false },
};

const SHOTS = [
  {
    file: "1-connections.png",
    title: "Connecting and disconnecting",
    text: "Settings, Connections. The member chooses to connect WHOOP with WHOOP's own sign-in, and can disconnect at any time with one tap. Disconnecting deletes the saved login straight away and stops all collection.",
  },
  {
    file: "2-home.png",
    title: "Home: the member's recovery, HRV and sleep",
    text: "The member's own WHOOP Recovery score with WHOOP's own colours (green 67 to 100, yellow 34 to 66, red 0 to 33), the metric kept under WHOOP's own name, and a \"DATA FROM WHOOP\" credit.",
  },
  {
    file: "3-readings.png",
    title: "Insights: all readings credited to WHOOP",
    text: "Each reading that comes from WHOOP (recovery, HRV, sleep, steps) carries a \"DATA FROM WHOOP\" credit, and shows the member's own change since yesterday.",
  },
  {
    file: "4-findings.png",
    title: "Findings: what affects this member",
    text: "The core of the app. Patterns are tested against the member's own history and explained in plain language, labelled as confirmed findings or early signals. It is for general wellness only and gives no medical advice.",
  },
  {
    file: "5-settings.png",
    title: "Member control: AI switch, export and delete",
    text: "Optional AI features can be switched off. The member can export a copy of their data and delete their account and every record we hold, from Settings.",
  },
  {
    file: "6-privacy.png",
    title: "Privacy policy",
    text: "Our privacy policy, updated 19 October 2026, available in the app and at app.causalme.com/privacy. It names WHOOP as a service the member may connect and explains what we collect and who handles it.",
  },
];

export default function WhoopIntegrationPage() {
  return (
    <div className="min-h-screen px-5 py-16" style={{ background: "#0b1015" }}>
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold mb-3" style={{ color: "#f2f6f8" }}>
          The Gap: WHOOP integration
        </h1>
        <p className="text-sm leading-relaxed mb-3" style={{ color: "#d3dde3" }}>
          The Gap is a wellness app for iPhone by Causal Me, an Australian sole trader. It helps a person find which of their own habits are associated with changes in their next-day recovery, HRV and sleep, by combining
          their own WHOOP data with what they log in the app and explaining each pattern in plain language. It is currently in private testing (TestFlight). These screenshots are from a real WHOOP member's account (the founder's).
        </p>
        <p className="text-sm leading-relaxed mb-8" style={{ color: "#d3dde3" }}>
          <strong style={{ color: "#f2f6f8" }}>WHOOP data used (scopes: read:recovery, read:sleep, read:cycles, offline):</strong> recovery score, HRV, resting heart rate; sleep duration, sleep stages and sleep performance; and, from the daily
          cycle, day strain, energy burned and step count where WHOOP returns it. We request nothing else. We store one summary value per day for each reading under the member's own account, never sell it, never use it
          for advertising and never show it to other members.
        </p>

        <div className="grid gap-10">
          {SHOTS.map((s) => (
            <figure key={s.file} className="flex flex-col sm:flex-row gap-5 items-start">
              <img
                src={`/whoop-integration/${s.file}`}
                alt={s.title}
                width={240}
                className="rounded-xl shrink-0"
                style={{ border: "1px solid rgba(255,255,255,0.12)", maxWidth: "100%", height: "auto" }}
              />
              <figcaption>
                <h2 className="text-lg font-semibold mb-1" style={{ color: "#f2f6f8" }}>
                  {s.title}
                </h2>
                <p className="text-sm leading-relaxed" style={{ color: "#d3dde3" }}>
                  {s.text}
                </p>
              </figcaption>
            </figure>
          ))}
        </div>

        <p className="text-sm leading-relaxed mt-12" style={{ color: "#9aa8b2" }}>
          Privacy policy: <a href="/privacy" style={{ color: "#22d3ee" }}>app.causalme.com/privacy</a> · Terms: <a href="/terms" style={{ color: "#22d3ee" }}>app.causalme.com/terms</a> · Contact:{" "}
          <a href="mailto:hello@causalme.com" style={{ color: "#22d3ee" }}>hello@causalme.com</a>
        </p>
      </div>
    </div>
  );
}
