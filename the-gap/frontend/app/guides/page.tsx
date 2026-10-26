import type { Metadata } from "next";
import { Breadcrumb, Card, Eyebrow, GetTheApp, H1, P, Wrap } from "../../components/site/parts";
import { GUIDES } from "../../lib/guides";

export const metadata: Metadata = {
  title: "Guides to your sleep and recovery data",
  description:
    "Plain-English guides from The Gap on heart rate variability, alcohol and sleep, and why correlation isn't the same as cause in your health data, with published sources.",
  alternates: { canonical: "/guides" },
};

export default function GuidesIndex() {
  return (
    <article className="pt-10 pb-6">
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "Guides" }]} />
        <div className="mt-6">
          <Eyebrow>Guides</Eyebrow>
          <H1>Understanding your sleep and recovery data</H1>
          <P>Plain-English explainers with published sources. General information, not medical advice.</P>
        </div>
        <div className="mt-8 grid gap-4">
          {GUIDES.map((g) => (
            <a key={g.slug} href={`/guides/${g.slug}`} className="block">
              <Card title={g.title}>
                <span className="block">{g.description}</span>
              </Card>
            </a>
          ))}
        </div>
        <GetTheApp />
      </Wrap>
    </article>
  );
}
