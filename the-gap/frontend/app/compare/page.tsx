import type { Metadata } from "next";
import { Breadcrumb, Eyebrow, GetTheApp, H1, H2, Note, P, UL, Wrap } from "../../components/site/parts";
import { DISCLAIMER } from "../../lib/site";

export const metadata: Metadata = {
  title: "The Gap vs your wearable's own app",
  description:
    "How The Gap differs from the insights in a wearable app such as Apple Health, Whoop or Oura: what each is good at, the different question The Gap answers, and why many people use both.",
  alternates: { canonical: "/compare" },
};

const ROWS: { label: string; wearable: string; gap: string }[] = [
  { label: "The main question", wearable: "What were my readings, and how do they compare with usual?", gap: "Why did my readings change?" },
  { label: "What it shows", wearable: "Scores, trends, sleep stages, strain, recovery", gap: "Findings about which of your habits seem to move your readings, each with a confidence label" },
  { label: "How patterns are found", wearable: "Varies by app: typically trends and comparisons over time", gap: "Statistical tests on your own days that adjust for other factors and for chance" },
  { label: "What you add", wearable: "Often little beyond what the device records", gap: "A 10-second daily check-in, food, water and workouts, so there is something to test" },
  { label: "Whose data it uses", wearable: "Yours", gap: "Yours, from several sources at once (Apple Health, Whoop, Oura, Strava, Withings, Polar)" },
  { label: "Time to useful answers", wearable: "Immediate for readings", gap: "A few weeks for confirmed findings, because honest answers need enough days" },
];

export default function ComparePage() {
  return (
    <article className="pt-10 pb-6">
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "Compare" }]} />
        <div className="mt-6">
          <Eyebrow>Compare</Eyebrow>
          <H1>The Gap vs your wearable&apos;s own app</H1>
          <P>
            They answer different questions, and they work well together. Your wearable&apos;s app is the best place to see what your body did. The Gap is for the follow-up: <em>why</em>.
          </P>
        </div>

        <div className="mt-8 overflow-x-auto rounded-2xl" style={{ border: "1px solid rgba(255,255,255,0.1)" }}>
          <table className="w-full text-sm" style={{ color: "#d3dde3" }}>
            <thead>
              <tr style={{ background: "rgba(255,255,255,0.06)" }}>
                <th className="text-left p-3 font-semibold" style={{ color: "#f2f6f8" }}></th>
                <th className="text-left p-3 font-semibold" style={{ color: "#f2f6f8" }}>A wearable&apos;s own app</th>
                <th className="text-left p-3 font-semibold" style={{ color: "#22d3ee" }}>The Gap</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.label} style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                  <td className="p-3 align-top font-semibold" style={{ color: "#f2f6f8" }}>{r.label}</td>
                  <td className="p-3 align-top">{r.wearable}</td>
                  <td className="p-3 align-top">{r.gap}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs" style={{ color: "#6f7f8a" }}>
          The left column describes wearable apps in general. Features vary from app to app and change over time, so check your own app for what it offers.
        </p>

        <H2>Use both</H2>
        <P>
          The Gap doesn&apos;t replace your wearable. It reads the data your wearable already collects and adds the context needed to look for reasons. If you already like your wearable&apos;s app, keep it for your day-to-day readings and use The Gap for the questions it raises.
        </P>

        <H2>When The Gap is a good fit</H2>
        <UL
          items={[
            "You often wonder what caused a low-recovery day or a short night.",
            "You use more than one device or app and want one place that brings the data together.",
            "You want to test your own habits, such as alcohol, caffeine, late meals or training load, against your own readings.",
            "You prefer a straight answer about how sure something is, including “not sure yet”.",
          ]}
        />

        <H2>When it isn&apos;t</H2>
        <UL
          items={[
            "You want a medical diagnosis or treatment plan. The Gap can’t provide that.",
            "You want instant answers on day one. Honest findings take a few weeks of data.",
            "You don’t want to log anything at all. The Gap works best with a short daily check-in.",
          ]}
        />
        <Note>{DISCLAIMER}</Note>
        <GetTheApp />
      </Wrap>
    </article>
  );
}
