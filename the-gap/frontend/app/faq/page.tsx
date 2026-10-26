import type { Metadata } from "next";
import { Breadcrumb, Eyebrow, GetTheApp, H1, JsonLd, P, Wrap } from "../../components/site/parts";
import { DISCLAIMER, SITE, TRADEMARK_NOTE } from "../../lib/site";

export const metadata: Metadata = {
  title: "The Gap FAQ",
  description:
    "Answers about The Gap: what it is, which wearables it works with, how long until the first insight, price, privacy, AI and how it differs from your wearable's own app.",
  alternates: { canonical: "/faq" },
};

const FAQ: { q: string; a: string }[] = [
  {
    q: "What is The Gap?",
    a: "The Gap is an iPhone app from CausalMe, an Australian company. It uses your own data from Apple Health, Apple Watch, Whoop, Oura, Strava, Withings and Polar, plus a quick daily check-in, to show what seems to affect your sleep, HRV and recovery. The idea is that a wearable shows what happened and The Gap helps you see why.",
  },
  {
    q: "Who is it for?",
    a: "Anyone who tracks their sleep, recovery or training and wants to understand what is behind their numbers: people with an Apple Watch, Whoop or Oura, and people with just an iPhone. It is built for people who want to understand their own patterns, not for diagnosing or treating anything.",
  },
  {
    q: "Which devices and apps does it work with?",
    a: "Apple Health (which brings in data from an Apple Watch and many other devices), Whoop, Oura, Strava, Withings and Polar. Direct Whoop and Oura connections have limited places at launch, but Apple Health always works. Garmin data can come in through Apple Health today; a direct Garmin connection is being built.",
  },
  {
    q: "Do I need a wearable?",
    a: "No. Without one, your iPhone still provides sleep and steps through Apple Health, and you can add a daily check-in and log food, water and workouts. More data means more patterns can be tested.",
  },
  {
    q: "How long until I see my first insight?",
    a: "Usually a few weeks. A pattern needs enough days with and without a habit, alongside the reading, to say anything honest. Until then The Gap shows tests running, with a counter of how far along each one is.",
  },
  {
    q: "How is The Gap different from my wearable's own app?",
    a: "Wearable apps are great at showing your readings, trends and scores. The Gap focuses on a different question: why a reading changed. It runs statistical tests on your own days that adjust for other factors and for chance, and labels each finding early or confirmed. Many people use both. See the comparison page for more.",
  },
  {
    q: "What does \"early\" versus \"confirmed\" mean?",
    a: "An early finding is a pattern that is showing but hasn't held up for long enough to be sure, so it's something to watch. A confirmed finding has passed checks that adjust for other things going on and for the chance of finding patterns by luck.",
  },
  {
    q: "Is it medical advice?",
    a: "No. " + DISCLAIMER + " It does not diagnose or treat anything and is not a medical device. If you are worried about your health, talk to a doctor.",
  },
  {
    q: "How much does it cost?",
    a: `The Gap is free to download, with your first month free. After that it is ${SITE.priceMonthly} a month or ${SITE.priceYearly} a year in Australian dollars, as an auto-renewing subscription through the App Store. You can cancel any time in your Apple ID settings.`,
  },
  {
    q: "What data does The Gap collect, and is it sold?",
    a: "It collects what you connect or log (for example sleep, heart rate, HRV, steps, check-ins, food and workouts) to find patterns for you. It is never sold and there is no advertising. The privacy policy lists exactly what is collected and the service providers that handle it.",
  },
  {
    q: "Does it use AI?",
    a: "Some features do. Gappy, the in-app assistant, and the reading of your written notes use an AI service, and only when you have switched AI features on. Short summaries are sent, never your name or email. The statistical analysis itself is done by The Gap's own engine, and you can switch AI features off at any time and keep using the rest of the app.",
  },
  {
    q: "Can I delete my data?",
    a: "Yes. In the app, Settings has options to export your data and to delete your account and data permanently, and you can disconnect any source at any time.",
  },
  {
    q: "Is there an Android version?",
    a: "Not yet. The Gap is on iPhone first, and Android is planned.",
  },
  {
    q: "Who makes The Gap?",
    a: "The Gap is made by CausalMe, a small Australian business based in Queensland. You can reach us at " + SITE.email + ".",
  },
];

export default function FaqPage() {
  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
  return (
    <article className="pt-10 pb-6">
      <JsonLd data={faq} />
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "FAQ" }]} />
        <div className="mt-6">
          <Eyebrow>FAQ</Eyebrow>
          <H1>Questions about The Gap</H1>
        </div>
        <div className="mt-8 space-y-7">
          {FAQ.map((f) => (
            <section key={f.q}>
              <h2 className="text-lg font-semibold" style={{ color: "#f2f6f8" }}>
                {f.q}
              </h2>
              <P>{f.a}</P>
            </section>
          ))}
        </div>
        <p className="mt-8 text-xs leading-relaxed" style={{ color: "#6f7f8a" }}>
          {TRADEMARK_NOTE}
        </p>
        <GetTheApp />
      </Wrap>
    </article>
  );
}
