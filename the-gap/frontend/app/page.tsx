import type { ReactNode } from "react";
import { HexGauge } from "../components/HexGauge";
import { Logo } from "../components/Logo";

const MAILTO = "mailto:hello@causalme.com?subject=Early%20access%20to%20The%20Gap";

const C = {
  text: "#f2f6f8",
  soft: "#d3dde3",
  muted: "#9aa8b2",
  faint: "#5f6d77",
  accent: "#22d3ee",
  good: "#34e07a",
  warn: "#fbbf24",
  surface: "rgba(255,255,255,0.05)",
  border: "rgba(255,255,255,0.08)",
};

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-bold tracking-[0.22em] mb-3" style={{ color: C.accent }}>
      {children}
    </p>
  );
}

function Card({ children, highlight }: { children: ReactNode; highlight?: boolean }) {
  return (
    <div
      className="rounded-2xl p-5"
      style={{
        background: highlight ? "rgba(34,211,238,0.08)" : C.surface,
        border: `1px solid ${highlight ? "rgba(34,211,238,0.35)" : C.border}`,
      }}
    >
      {children}
    </div>
  );
}

/** A made-up phone screen, clearly labelled as an illustration. */
function PhoneMock() {
  return (
    <div className="relative mx-auto w-[310px]">
      <div
        className="rounded-[42px] p-3"
        style={{
          background: "linear-gradient(160deg,#1c262e,#0d1318)",
          border: "1px solid rgba(255,255,255,0.10)",
          boxShadow: "0 40px 90px rgba(34,211,238,0.14)",
        }}
      >
        <div className="rounded-[32px] px-4 pt-6 pb-5" style={{ background: "#0b1015" }}>
          <p className="text-[10px] font-bold tracking-[0.2em]" style={{ color: C.accent }}>
            TODAY
          </p>
          <div className="mt-3 flex items-start justify-between px-1">
            <HexGauge size={84} progress={0.72} value="62" unit="ms" label="HRV" color={C.good} />
            <div className="mt-4">
              <HexGauge size={84} progress={0.8} value="7.4" unit="hrs" label="Sleep" color={C.accent} />
            </div>
            <HexGauge size={84} progress={0.55} value="5.2k" unit="steps" label="Steps" color={C.warn} />
          </div>

          <div className="mt-5 rounded-2xl p-3.5" style={{ background: "rgba(34,211,238,0.10)", border: "1px solid rgba(34,211,238,0.35)" }}>
            <p className="text-[10px] font-bold tracking-[0.2em]" style={{ color: C.accent }}>
              NEW DISCOVERY
            </p>
            <p className="mt-1.5 text-[13px] leading-snug" style={{ color: C.text }}>
              On nights you have a drink, your HRV the next morning is about 6 ms lower.
            </p>
            <p className="mt-2 text-[11px]" style={{ color: C.muted }}>
              Moderate confidence
            </p>
          </div>

          <div className="mt-3 rounded-2xl p-3.5" style={{ background: C.surface, border: `1px solid ${C.border}` }}>
            <p className="text-[10px] font-bold tracking-[0.2em]" style={{ color: C.accent }}>
              TODAY&apos;S PLAN
            </p>
            <p className="mt-1.5 text-[13px] leading-snug" style={{ color: C.soft }}>
              Rest day planned, but your recovery looks strong. A steady session would suit you.
            </p>
          </div>
        </div>
      </div>
      <p className="mt-3 text-center text-[11px]" style={{ color: C.faint }}>
        Illustration with example numbers
      </p>
    </div>
  );
}

const STEPS = [
  {
    n: "1",
    title: "Connect what you already use",
    text: "Apple Health, Whoop, Oura, Strava, Withings, Polar and your calendar. Read-only: The Gap never writes to them.",
  },
  {
    n: "2",
    title: "Log what wearables can't see",
    text: "A 30-second daily check-in (alcohol, caffeine, energy drinks, work, stress, travel), plus food, water and workouts.",
  },
  {
    n: "3",
    title: "Get findings that are about you",
    text: "After a few weeks The Gap tests which habits really change your recovery and tells you in plain English what to try.",
  },
];

const FEATURES = [
  {
    title: "Sealed discoveries",
    text: "When something new is found, it arrives as a sealed box. Tap to open a plain-English story with things you can try.",
  },
  {
    title: "Honest confidence",
    text: "Every finding is labelled. “Confirmed” has passed a stricter test. An “early signal” is a hint worth watching, not a conclusion.",
  },
  {
    title: "Today's plan",
    text: "Train, go light or rest, based on your recovery compared with your own normal, the week you've set, and what you've logged.",
  },
  {
    title: "Your Health tab",
    text: "Food and water logging, a workout builder with exercise pictures, a timer for every set, and heart-rate-aware suggestions with a watch.",
  },
  {
    title: "Ideas each week",
    text: "Fresh food ideas, recipes and workout videos matched to your goal, your diet and the equipment you have. New ones every Monday.",
  },
  {
    title: "Ask Gappy",
    text: "Ask questions about your own data. The AI assistant is optional and can be switched off in Settings.",
  },
];

const FAQ = [
  {
    q: "Is The Gap on the App Store?",
    a: "Not yet. It's in private testing on iPhone. Email hello@causalme.com to ask for early access.",
  },
  {
    q: "Do I need a wearable?",
    a: "You need an iPhone. Apple Health data works on its own, and a watch or ring such as an Apple Watch, Whoop or Oura gives the fullest picture.",
  },
  {
    q: "How long until I see findings?",
    a: "Early signals can appear within a couple of weeks. Most confirmed findings need about 30 days of data, and The Gap tells you when there isn't enough yet instead of guessing.",
  },
  {
    q: "Is it medical advice?",
    a: "No. The Gap gives general information about your own data. It doesn't diagnose or treat anything. Speak to a health professional about medical questions.",
  },
  {
    q: "What does it cost?",
    a: "The Gap is a paid subscription in the app. The price and terms are shown before you buy, and you can cancel any time in your iPhone's Settings.",
  },
  {
    q: "What happens to my data?",
    a: "It's never sold and there are no ads. AI features are optional. You can delete your account and data from inside the app. The Privacy Policy has the details.",
  },
];

export default function LandingPage() {
  return (
    <div className="relative overflow-hidden" style={{ background: "#0b1015", color: C.text }}>
      {/* Soft teal glows from the top and bottom edges, as in the app */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[620px]"
        style={{ background: "radial-gradient(60% 100% at 50% 0%, rgba(20,184,198,0.30), transparent 70%)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[420px]"
        style={{ background: "radial-gradient(60% 100% at 50% 100%, rgba(20,184,198,0.12), transparent 70%)" }}
      />

      {/* Hero */}
      <section className="relative mx-auto max-w-5xl px-5 pt-16 pb-20 md:pt-24">
        <div className="grid items-center gap-14 md:grid-cols-2">
          <div>
            <span
              className="inline-block rounded-full px-3 py-1 text-xs font-semibold"
              style={{ border: "1px solid rgba(34,211,238,0.4)", color: C.accent, background: "rgba(34,211,238,0.08)" }}
            >
              Private testing on iPhone
            </span>
            <h1 className="mt-6 text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl md:text-[3.4rem]">
              Don&apos;t just know what.
              <br />
              <span style={{ color: C.accent }}>Know why.</span>
            </h1>
            <p className="mt-6 max-w-md text-base leading-relaxed sm:text-lg" style={{ color: C.soft }}>
              Your wearable can tell you your HRV dropped. The Gap works out what&apos;s behind it, using your own sleep, training, food and daily habits, not averages from other people.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a
                href={MAILTO}
                className="rounded-full px-6 py-3 text-sm font-bold transition-opacity hover:opacity-90"
                style={{ background: C.accent, color: "#04141a" }}
              >
                Ask for early access
              </a>
              <a
                href="#how"
                className="rounded-full px-6 py-3 text-sm font-semibold transition-colors hover:bg-white/5"
                style={{ border: "1px solid rgba(255,255,255,0.18)", color: C.text }}
              >
                See how it works
              </a>
            </div>
            <p className="mt-4 text-xs" style={{ color: C.faint }}>
              Not on the App Store yet. We only use your email to reply to you.
            </p>
          </div>
          <PhoneMock />
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="relative mx-auto max-w-5xl px-5 py-16">
        <Eyebrow>HOW IT WORKS</Eyebrow>
        <h2 className="max-w-xl text-3xl font-bold tracking-tight sm:text-4xl">Three steps, then it does the work.</h2>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <Card key={s.n}>
              <span
                className="flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold"
                style={{ background: "rgba(34,211,238,0.12)", color: C.accent, border: "1px solid rgba(34,211,238,0.35)" }}
              >
                {s.n}
              </span>
              <h3 className="mt-4 text-lg font-semibold">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: C.muted }}>
                {s.text}
              </p>
            </Card>
          ))}
        </div>
        <p className="mt-6 text-sm" style={{ color: C.muted }}>
          Works with: Apple Health · Apple Watch · Whoop · Oura · Strava · Withings · Polar · Google Calendar
        </p>
      </section>

      {/* Features */}
      <section className="relative mx-auto max-w-5xl px-5 py-16">
        <Eyebrow>WHAT&apos;S INSIDE</Eyebrow>
        <h2 className="max-w-xl text-3xl font-bold tracking-tight sm:text-4xl">Built to explain your body, not just chart it.</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title}>
              <h3 className="text-base font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: C.muted }}>
                {f.text}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* Method */}
      <section className="relative mx-auto max-w-5xl px-5 py-16">
        <div className="grid items-start gap-10 md:grid-cols-2">
          <div>
            <Eyebrow>THE IDEA</Eyebrow>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Not averages. You.</h2>
            <p className="mt-4 text-base leading-relaxed" style={{ color: C.soft }}>
              Most health advice comes from studies of other people. The Gap looks at your own days: what you did, how you slept, and how you recovered, and asks which habits really make the difference for you.
            </p>
          </div>
          <div className="space-y-3">
            {[
              "It compares your own days with each other, not with a population.",
              "It allows for other things that changed, like how long you slept or what day of the week it was.",
              "It tells you how sure it is, and says “not enough data yet” instead of guessing.",
            ].map((t) => (
              <div key={t} className="flex gap-3 rounded-2xl p-4" style={{ background: C.surface, border: `1px solid ${C.border}` }}>
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: C.good }} />
                <p className="text-sm leading-relaxed" style={{ color: C.soft }}>
                  {t}
                </p>
              </div>
            ))}
            <p className="px-1 pt-1 text-xs leading-relaxed" style={{ color: C.faint }}>
              It finds patterns in your data. It can&apos;t prove cause the way a lab trial can, which is why findings come with confidence labels and ideas to test for yourself.
            </p>
          </div>
        </div>
      </section>

      {/* Privacy */}
      <section className="relative mx-auto max-w-5xl px-5 py-16">
        <Card highlight>
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="max-w-xl">
              <Eyebrow>YOUR DATA STAYS YOURS</Eyebrow>
              <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Private by design.</h2>
              <ul className="mt-4 space-y-2 text-sm leading-relaxed" style={{ color: C.soft }}>
                <li>• Never sold, no ads, and no tracking tools in the app.</li>
                <li>• Apple Health access is read-only.</li>
                <li>• AI features are optional. Switch them off and nothing is sent to an AI service.</li>
                <li>• Delete your account and data any time from inside the app.</li>
              </ul>
            </div>
            <a
              href="/privacy"
              className="shrink-0 rounded-full px-6 py-3 text-center text-sm font-semibold transition-colors hover:bg-white/5"
              style={{ border: "1px solid rgba(255,255,255,0.18)", color: C.text }}
            >
              Read the Privacy Policy
            </a>
          </div>
        </Card>
      </section>

      {/* FAQ */}
      <section className="relative mx-auto max-w-3xl px-5 py-16">
        <Eyebrow>QUESTIONS</Eyebrow>
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Good to know.</h2>
        <div className="mt-8 divide-y" style={{ borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }}>
          {FAQ.map((f) => (
            <details key={f.q} className="group py-4" style={{ borderColor: C.border }}>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-base font-semibold">
                {f.q}
                <span className="text-xl transition-transform group-open:rotate-45" style={{ color: C.accent }} aria-hidden>
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed" style={{ color: C.muted }}>
                {f.a}
              </p>
            </details>
          ))}
        </div>
      </section>

      {/* Closing */}
      <section className="relative mx-auto max-w-3xl px-5 pb-8 pt-12 text-center">
        <Logo size={64} className="mx-auto" />
        <h2 className="mt-6 text-3xl font-bold tracking-tight sm:text-4xl">Want to try it early?</h2>
        <p className="mx-auto mt-3 max-w-md text-base" style={{ color: C.soft }}>
          We&apos;re letting a small number of people in while we get it right.
        </p>
        <a
          href={MAILTO}
          className="mt-8 inline-block rounded-full px-8 py-3.5 text-sm font-bold transition-opacity hover:opacity-90"
          style={{ background: C.accent, color: "#04141a" }}
        >
          Email us for early access
        </a>
      </section>
    </div>
  );
}
