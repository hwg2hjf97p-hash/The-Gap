"use client";

import { useEffect, useState } from "react";
import { getUserId } from "../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

type Insight = {
  hypothesis_id: string;
  title: string;
  headline: string;
  body: string;
  metric_delta: string;
  metric_unit: string;
  metric_direction: "positive" | "negative";
  confidence: string;
  confidence_label: string;
  category?: string;
};

const CATEGORIES = ["All", "Sleep", "Energy", "Focus", "Stress", "Health", "Work", "Lifestyle", "Recovery"];

export default function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState("All");

  useEffect(() => {
    const uid = getUserId();
    fetch(`${API_URL}/results/latest/${uid}`)
      .then((r) => r.json())
      .then((data) => setInsights(data.insights ?? []))
      .catch(() => setInsights([]))
      .finally(() => setLoading(false));
  }, []);

  const availableCategories = [
    "All",
    ...Array.from(new Set(insights.map((i) => i.category).filter(Boolean))) as string[],
  ];

  const filtered =
    activeCategory === "All"
      ? insights
      : insights.filter((i) => (i.category || "").toLowerCase() === activeCategory.toLowerCase());

  return (
    <div className="min-h-screen" style={{ background: "#0a1710" }}>
      <div className="max-w-lg mx-auto px-5 py-8">
        <p className="text-xs font-mono tracking-widest mb-3" style={{ color: "#c9a84c" }}>
          YOUR CAUSAL LIBRARY
        </p>
        <h1 className="text-3xl font-bold mb-2" style={{ color: "#eef3f0" }}>
          What we know about you
        </h1>
        <p className="text-sm mb-6" style={{ color: "#a2bcaf" }}>
          {insights.length} verified causal fact{insights.length !== 1 ? "s" : ""}. Not correlations.
        </p>

        {/* Category filter */}
        <div className="flex gap-2 overflow-x-auto mb-6 pb-1">
          {availableCategories.map((cat) => {
            const isActive = cat === activeCategory;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className="px-4 py-2 rounded-full text-sm font-medium flex-shrink-0"
                style={{
                  background: isActive ? "transparent" : "#132c1f",
                  border: `1px solid ${isActive ? "#c9a84c" : "#1a3d2b"}`,
                  color: isActive ? "#c9a84c" : "#a2bcaf",
                }}
              >
                {cat}
              </button>
            );
          })}
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl p-6 text-center" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <p style={{ color: "#a2bcaf" }}>
              {insights.length === 0
                ? "No verified insights yet — check back as more days of data come in."
                : "Nothing in this category yet."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((insight) => (
              <div
                key={insight.hypothesis_id}
                className="rounded-2xl p-5"
                style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold tracking-wide" style={{ color: "#c9a84c" }}>
                    {(insight.category || "INSIGHT").toUpperCase()}
                  </span>
                  <span className="text-sm" style={{ color: "#a2bcaf" }}>
                    {Math.round(parseFloat(insight.confidence) * 100) || insight.confidence}% confidence
                  </span>
                </div>
                <h3 className="font-semibold mb-2" style={{ color: "#eef3f0" }}>
                  {insight.headline}
                </h3>
                <p className="text-sm mb-3" style={{ color: "#a2bcaf" }}>
                  {insight.body}
                </p>
                <span
                  className="text-xs px-3 py-1 rounded-full"
                  style={{
                    background:
                      insight.metric_direction === "positive" ? "rgba(52,211,153,0.1)" : "rgba(248,113,113,0.1)",
                    color: insight.metric_direction === "positive" ? "#34d399" : "#f87171",
                  }}
                >
                  {insight.metric_direction === "positive" ? "+" : "−"}
                  {insight.metric_delta} {insight.metric_unit}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
