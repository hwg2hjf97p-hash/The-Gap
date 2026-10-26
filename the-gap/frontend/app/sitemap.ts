import type { MetadataRoute } from "next";
import { GUIDES } from "../lib/guides";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://causalme.com";
  return [
    { url: `${base}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${base}/how-it-works`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/faq`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/compare`, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/guides`, changeFrequency: "monthly", priority: 0.7 },
    ...GUIDES.map((g) => ({ url: `${base}/guides/${g.slug}`, changeFrequency: "yearly" as const, priority: 0.6 })),
    { url: `${base}/press`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${base}/privacy`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${base}/terms`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
