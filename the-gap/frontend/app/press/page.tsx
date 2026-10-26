import type { Metadata } from "next";
import { Breadcrumb, Card, Eyebrow, H1, H2, P, UL, Wrap } from "../../components/site/parts";
import { APP_LIVE, SITE, TRADEMARK_NOTE } from "../../lib/site";

export const metadata: Metadata = {
  title: "Press kit",
  description:
    "Facts, a short description, logos and contact details for writing about The Gap, the iPhone app by CausalMe that shows what seems to affect your sleep and recovery.",
  alternates: { canonical: "/press" },
};

export default function PressPage() {
  return (
    <article className="pt-10 pb-6">
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "Press" }]} />
        <div className="mt-6">
          <Eyebrow>Press kit</Eyebrow>
          <H1>The Gap: facts for writers</H1>
          <P>Everything here can be quoted. If you need something else, email {SITE.email}.</P>
        </div>

        <H2>In one paragraph</H2>
        <P>
          The Gap is an iPhone app from the Australian company CausalMe. It uses a person&apos;s own data from Apple Health, Apple Watch, Whoop, Oura, Strava, Withings and Polar, plus a quick daily check-in, to show what seems to affect their sleep, heart rate variability and recovery. Where most health apps show that two things move together, The Gap runs statistical tests on each person&apos;s own days that adjust for other factors and for chance, and labels every finding early or confirmed. It gives general information and is not medical advice.
        </P>

        <H2>Key facts</H2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Card title="Name">The Gap (the app by CausalMe)</Card>
          <Card title="Platform">{SITE.platform}. Android is planned.</Card>
          <Card title="Status">{APP_LIVE ? "Available on the Apple App Store." : "Launching on the Apple App Store soon."}</Card>
          <Card title="Price">Free to download. First month free, then {SITE.priceMonthly} a month or {SITE.priceYearly} a year (AUD), auto-renewing, cancel any time.</Card>
          <Card title="Based in">Queensland, Australia</Card>
          <Card title="Contact">{SITE.email}</Card>
        </div>

        <H2>What makes it different</H2>
        <UL
          items={[
            "It analyses your own data, not averages from other people.",
            "It tests for cause, not just correlation: findings adjust for other factors and for chance, and carry a confidence label (early or confirmed).",
            "It is honest about timing: first patterns usually take a few weeks.",
            "Your data isn’t sold, there is no advertising, and AI features are optional.",
          ]}
        />

        <H2>Logos</H2>
        <P muted>Free to use when writing about The Gap.</P>
        <div className="mt-3 flex flex-wrap items-center gap-6">
          <a href="/garmin-logo-300.png" download>
            <img src="/garmin-logo-300.png" width={120} height={120} alt="The Gap logo, 300 by 300 pixels" style={{ borderRadius: 24 }} />
            <span className="block mt-2 text-xs" style={{ color: "#22d3ee" }}>Download (300 × 300 PNG)</span>
          </a>
        </div>
        <P muted>Screenshots and a larger logo are available on request.</P>

        <H2>About the name</H2>
        <P>
          &quot;The Gap&quot; refers to the gap between correlation and cause. Please call it &quot;The Gap app by CausalMe&quot; or &quot;CausalMe&apos;s The Gap&quot; to avoid confusion with other businesses of a similar name.
        </P>

        <p className="mt-8 text-xs leading-relaxed" style={{ color: "#6f7f8a" }}>
          {TRADEMARK_NOTE}
        </p>
      </Wrap>
    </article>
  );
}
