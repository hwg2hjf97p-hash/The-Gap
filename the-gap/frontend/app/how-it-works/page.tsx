import type { Metadata } from "next";
import { Breadcrumb, Eyebrow, GetTheApp, H1, H2, JsonLd, Note, P, UL, Wrap } from "../../components/site/parts";
import { DISCLAIMER, SITE } from "../../lib/site";

export const metadata: Metadata = {
  title: "How The Gap works",
  description:
    "How The Gap finds what seems to affect your sleep and recovery: it connects your data, adds a quick daily check-in, tests habits against your own readings, and labels findings early or confirmed.",
  alternates: { canonical: "/how-it-works" },
};

export default function HowItWorks() {
  const crumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "The Gap", item: SITE.url },
      { "@type": "ListItem", position: 2, name: "How it works", item: `${SITE.url}/how-it-works` },
    ],
  };
  return (
    <article className="pt-10 pb-6">
      <JsonLd data={crumbs} />
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "How it works" }]} />
        <div className="mt-6">
          <Eyebrow>How it works</Eyebrow>
          <H1>From numbers to reasons</H1>
          <P>
            A wearable tells you what happened: your recovery was low, your sleep was short. It can&apos;t tell you why. The Gap works on that gap, using the data you already have plus a little you add each day.
          </P>
        </div>

        <H2>1. It connects what you already use</H2>
        <P>
          Connect Apple Health, which brings in data from an Apple Watch and many other devices, and, if you use them, Whoop, Oura, Strava, Withings or Polar. The Gap reads your own sleep, resting heart rate, HRV, steps and workouts. You choose which device is the main source for each kind of reading. If you have no wearable, your iPhone still provides sleep and steps through Apple Health.
        </P>

        <H2>2. You add a little context</H2>
        <P>
          Numbers alone can&apos;t explain themselves, so a 10-second daily check-in records the things that tend to matter: stress, alcohol, caffeine, screen time, a busy day, travel. You can also log food, water and workouts, by tapping, typing, or saying &quot;Hey Siri, log to The Gap&quot;. You choose which questions appear and can switch any of them off.
        </P>

        <H2>3. It tests, not just compares</H2>
        <P>
          Plenty of apps can show that two things move together. But two things moving together doesn&apos;t mean one causes the other: a stressful day might cause both a late dinner and a poor night&apos;s sleep. The Gap runs a statistical test on <strong style={{ color: "#f2f6f8" }}>your</strong> days that tries to separate the two. For each habit it asks whether it seems to change a reading, once other things going on (like the day of the week and how you slept the night before) are taken into account. It also corrects for the fact that if you test many patterns, some will look real by luck.
        </P>
        <Note>
          This is analysis of everyday data, not a controlled experiment, so it can show what seems to affect you, not prove it. That&apos;s why every finding carries a confidence label.
        </Note>

        <H2>4. It tells you how sure it is</H2>
        <UL
          items={[
            <><strong style={{ color: "#f2f6f8" }}>Early</strong>: a pattern is showing but hasn&apos;t held up for long enough yet. Worth watching, not worth acting on.</>,
            <><strong style={{ color: "#f2f6f8" }}>Confirmed</strong>: it has held up and passed the checks. These open as discoveries.</>,
            <><strong style={{ color: "#f2f6f8" }}>Tests running</strong>: patterns that need more days of data, with a counter showing how far along each one is.</>,
          ]}
        />

        <H2>5. Why it takes a few weeks</H2>
        <P>
          A pattern needs enough days with <em>and</em> without the habit, alongside the reading, to say anything honest. For most habits that means a few weeks. Anything faster would be guessing, and The Gap is built not to guess. You can filter your insights by what they affect (for example HRV) or by the habit behind them (for example alcohol).
        </P>

        <H2>6. Food and training, too</H2>
        <P>
          Log what you eat and drink, with calories, protein, carbs, fat and sugar shown for the day, and set goals for protein, water and sugar. Train with ready-made workouts or your own, with suggested weights from your own lifts. All of it feeds the analysis, so The Gap can test things like whether a late dinner changes your deep sleep, or whether more protein lifts your next-day HRV.
        </P>

        <H2>7. You stay in control</H2>
        <UL
          items={[
            "Your data isn’t sold, and there is no advertising.",
            "AI features (such as Gappy, the in-app assistant, and the reading of your written notes) are optional and can be switched off. The statistics themselves are done by The Gap’s own engine, not by AI.",
            "You can export or permanently delete your data from inside the app, and disconnect any source at any time.",
            <>See the <a href="/privacy" style={{ color: "#22d3ee", textDecoration: "underline" }}>privacy policy</a> for exactly what is collected and who handles it.</>,
          ]}
        />

        <H2>What it can&apos;t do</H2>
        <UL
          items={[
            "It can’t diagnose or treat anything, and it isn’t a medical device.",
            "It can’t tell you what to do about a finding. A finding is something to think about, and to bring to a doctor, dietitian or coach if it matters.",
            "It can’t see anything you don’t log or connect.",
          ]}
        />
        <P muted>{DISCLAIMER}</P>
        <GetTheApp />
      </Wrap>
    </article>
  );
}
