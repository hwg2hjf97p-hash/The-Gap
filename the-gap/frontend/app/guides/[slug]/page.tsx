import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Breadcrumb, Eyebrow, GetTheApp, H1, H2, JsonLd, Note, P, UL, Wrap } from "../../../components/site/parts";
import { GUIDES } from "../../../lib/guides";
import { DISCLAIMER, SITE } from "../../../lib/site";

export function generateStaticParams() {
  return GUIDES.map((g) => ({ slug: g.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const guide = GUIDES.find((g) => g.slug === params.slug);
  if (!guide) return {};
  return {
    title: guide.title,
    description: guide.description,
    alternates: { canonical: `/guides/${guide.slug}` },
    openGraph: { title: guide.title, description: guide.description, type: "article", url: `${SITE.url}/guides/${guide.slug}` },
  };
}

export default function GuidePage({ params }: { params: { slug: string } }) {
  const guide = GUIDES.find((g) => g.slug === params.slug);
  if (!guide) notFound();

  const article = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: guide.headline,
    description: guide.description,
    datePublished: guide.published,
    dateModified: guide.published,
    inLanguage: "en-AU",
    mainEntityOfPage: `${SITE.url}/guides/${guide.slug}`,
    author: { "@type": "Organization", name: "CausalMe", url: SITE.url },
    publisher: { "@type": "Organization", name: "CausalMe", url: SITE.url },
    citation: guide.references.map((r) => r.url),
  };
  const crumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "The Gap", item: SITE.url },
      { "@type": "ListItem", position: 2, name: "Guides", item: `${SITE.url}/guides` },
      { "@type": "ListItem", position: 3, name: guide.title, item: `${SITE.url}/guides/${guide.slug}` },
    ],
  };

  return (
    <article className="pt-10 pb-6">
      <JsonLd data={article} />
      <JsonLd data={crumbs} />
      <Wrap narrow>
        <Breadcrumb items={[{ name: "The Gap", href: "/" }, { name: "Guides", href: "/guides" }, { name: guide.title }]} />
        <div className="mt-6">
          <Eyebrow>Guide</Eyebrow>
          <H1>{guide.headline}</H1>
          <p className="mt-3 text-xs" style={{ color: "#9aa8b2" }}>
            By CausalMe · Written {new Date(guide.published).toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" })}
          </p>
          <P>{guide.intro}</P>
        </div>

        {guide.sections.map((s) => (
          <section key={s.heading}>
            <H2>{s.heading}</H2>
            {s.paragraphs?.map((p) => (
              <P key={p}>{p}</P>
            ))}
            {s.bullets && <UL items={s.bullets} />}
          </section>
        ))}

        <Note>{DISCLAIMER}</Note>

        <H2>References</H2>
        <ol className="mt-3 space-y-2 pl-5 list-decimal text-sm leading-relaxed" style={{ color: "#c3cfd6" }}>
          {guide.references.map((r) => (
            <li key={r.url}>
              {r.text}{" "}
              <a href={r.url} style={{ color: "#22d3ee", textDecoration: "underline" }} rel="noopener noreferrer">
                Source
              </a>
            </li>
          ))}
        </ol>

        <H2>See it in your own data</H2>
        <P>
          The Gap tests which of your habits seem to move your sleep, HRV and recovery, and tells you how sure it is. <a href="/how-it-works" style={{ color: "#22d3ee", textDecoration: "underline" }}>How it works</a>.
        </P>
        <GetTheApp />
      </Wrap>
    </article>
  );
}
