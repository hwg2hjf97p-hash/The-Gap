import type { Metadata } from "next";
import { Logo } from "../components/Logo";
import { Card, Eyebrow, GetTheApp, H1, H2, JsonLd, Note, P, Wrap } from "../components/site/parts";
import { APP_LIVE, DISCLAIMER, SITE, TRADEMARK_NOTE, WORKS_WITH } from "../lib/site";

export const metadata: Metadata = {
  title: { absolute: "The Gap: find what really affects your sleep and recovery | The Gap app by CausalMe" },
  description:
    "The Gap is an iPhone app that uses your own data from Apple Health, Apple Watch, Whoop, Oura and more to show what seems to affect your sleep, HRV and recovery. First month free.",
  alternates: { canonical: "/" },
};

const FEATURES: { title: string; text: string }[] = [
  { title: "Your day at a glance", text: "Sleep, recovery and HRV from the sources you connect, compared with your own normal for that day of the week, with a short plain-English note." },
  { title: "A 10-second daily check-in", text: "Stress, alcohol, caffeine, screen time, a busy day, travel. Or say \"Hey Siri, log to The Gap\" for water, coffee, food or a note." },
  { title: "Discoveries from your own data", text: "When a pattern in your own days holds up, it opens as a discovery. Findings are labelled early or confirmed, so you always know how sure it is." },
  { title: "Nutrition", text: "Log food by search, barcode, or just describe the meal. See calories, protein, carbs, fat and sugar for the day, and set goals for protein, water and sugar." },
  { title: "Training", text: "Ready-made workouts or your own, suggested weights each session based on your own lifts, a weekly workout ring, personal bests and multi-week programs." },
  { title: "Gappy, your assistant", text: "Ask a question in plain words about your own sleep, recovery or habits and get an answer based on your data. AI features are optional and can be switched off." },
];

export default function Home() {
  const app = {
    "@context": "https://schema.org",
    "@type": "MobileApplication",
    name: SITE.name,
    alternateName: SITE.fullName,
    description:
      "An iPhone app that finds what seems to affect your sleep, HRV and recovery, using your own data from Apple Health, Apple Watch, Whoop, Oura, Strava, Withings and Polar.",
    operatingSystem: "iOS",
    applicationCategory: "HealthApplication",
    inLanguage: "en-AU",
    url: SITE.url,
    publisher: { "@type": "Organization", name: "CausalMe", url: SITE.url },
    offers: { "@type": "Offer", price: "0", priceCurrency: SITE.currency, description: `Free to download. First month free, then ${SITE.priceMonthly} a month or ${SITE.priceYearly} a year (auto-renewing subscription, cancel any time).` },
    ...(APP_LIVE ? { downloadUrl: SITE.appStoreUrl, installUrl: SITE.appStoreUrl } : {}),
  };
  const org = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "CausalMe",
    url: SITE.url,
    logo: `${SITE.url}/garmin-logo-300.png`,
    email: SITE.email,
    areaServed: "AU",
    makesOffer: { "@type": "Offer", itemOffered: { "@type": "MobileApplication", name: SITE.name } },
  };

  return (
    <>
      <JsonLd data={app} />
      <JsonLd data={org} />

      <section className="pt-10 sm:pt-16 pb-6">
        <Wrap>
          <div className="flex flex-col sm:flex-row items-center gap-10">
            <div className="flex-1 text-center sm:text-left">
              <Eyebrow>The Gap app by CausalMe</Eyebrow>
              <H1>Don&apos;t just know what. Know why.</H1>
              <P>
                Your watch shows what happened. <strong style={{ color: "#f2f6f8" }}>The Gap</strong> helps you find what&apos;s behind it, using <strong style={{ color: "#f2f6f8" }}>your own data</strong>, not averages from other people. It&apos;s an iPhone app that works out which of your habits seem to move your sleep, HRV and recovery.
              </P>
              <GetTheApp />
            </div>
            <div className="shrink-0">
              <Logo size={220} />
            </div>
          </div>
        </Wrap>
      </section>

      <section>
        <Wrap>
          <H2 id="how">How it works</H2>
          <div className="grid gap-4 sm:grid-cols-3 mt-4">
            <Card title="1. Connect">Link Apple Health (which brings in Apple Watch data), or Whoop, Oura, Strava, Withings or Polar. No wearable? Your iPhone still gives sleep and steps.</Card>
            <Card title="2. Check in">A quick daily check-in and easy logging of food, water and workouts, by tapping, typing or talking to Siri.</Card>
            <Card title="3. Discover">The Gap tests which habits seem to change your numbers, and shows you the ones that hold up in your own data.</Card>
          </div>
          <P muted>
            <a href="/how-it-works" style={{ color: "#22d3ee", textDecoration: "underline" }}>
              Read how it works in plain English
            </a>
          </P>
        </Wrap>
      </section>

      <section>
        <Wrap>
          <H2>What&apos;s inside</H2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-4">
            {FEATURES.map((f) => (
              <Card key={f.title} title={f.title}>
                {f.text}
              </Card>
            ))}
          </div>
        </Wrap>
      </section>

      <section>
        <Wrap>
          <H2>Honest by design</H2>
          <div className="grid gap-4 sm:grid-cols-2 mt-4">
            <Card title="Early or confirmed">A pattern is called early until it has held up for long enough, and confirmed only after it passes checks that adjust for other things going on and for the chance of finding patterns by luck.</Card>
            <Card title="It takes a few weeks">The first patterns usually need a few weeks of days with both the habit and the reading. The Gap tells you how far along each one is, instead of guessing.</Card>
            <Card title="Your data, your control">Your data isn&apos;t sold and there are no ads. You can export or delete everything from inside the app, and AI features can be switched off.</Card>
            <Card title="Not medical advice">{DISCLAIMER}</Card>
          </div>
        </Wrap>
      </section>

      <section>
        <Wrap>
          <H2>Works with</H2>
          <P>{WORKS_WITH.join(", ")}.</P>
          <P muted>
            Garmin data can come in through Apple Health today (some measures, such as HRV, may not). A direct Garmin connection is being built. Direct Whoop and Oura connections have limited places at launch; Apple Health always works.
          </P>
          <p className="mt-3 text-xs leading-relaxed" style={{ color: "#6f7f8a" }}>
            {TRADEMARK_NOTE}
          </p>
        </Wrap>
      </section>

      <section>
        <Wrap>
          <H2>Price</H2>
          <P>
            Free to download, with <strong style={{ color: "#f2f6f8" }}>your first month free</strong>. After that it&apos;s {SITE.priceMonthly} a month or {SITE.priceYearly} a year (Australian dollars), as an auto-renewing subscription through the App Store. You can cancel any time in your Apple ID settings.
          </P>
          <Note>
            Questions? Read the <a href="/faq" style={{ color: "#22d3ee", textDecoration: "underline" }}>FAQ</a>, see <a href="/compare" style={{ color: "#22d3ee", textDecoration: "underline" }}>how The Gap compares with your wearable&apos;s own app</a>, or browse the <a href="/guides" style={{ color: "#22d3ee", textDecoration: "underline" }}>guides</a>.
          </Note>
          <GetTheApp compact />
        </Wrap>
      </section>
    </>
  );
}
