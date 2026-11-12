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
    <div className="min-h-screen" style={{ background: "#16130f" }}>
      <div className="max-w-lg mx-auto px-5 py-8">
        <p className="text-xs font-mono tracking-widest mb-3" style={{ color: "#e0a458" }}>
          YOUR CAUSAL LIBRARY
        </p>
        <h1 className="text-3xl font-bold mb-2" style={{ color: "#f1ebe2" }}>
          What we know about you
        </h1>
        <p className="text-sm mb-6" style={{ color: "#a0968a" }}>
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
                  background: isActive ? "transparent" : "#211d18",
                  border: `1px solid ${isActive ? "#e0a458" : "#2f2a23"}`,
                  color: isActive ? "#e0a458" : "#a0968a",
                }}
              >
                {cat}
              </button>
            );
          })}
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "#e0a458", borderTopColor: "transparent" }} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl p-6 text-center" style={{ background: "#211d18", border: "1px solid #2f2a23" }}>
            <p style={{ color: "#a0968a" }}>
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
                style={{ background: "#211d18", border: "1px solid #2f2a23" }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold tracking-wide" style={{ color: "#e0a458" }}>
                    {(insight.category || "INSIGHT").toUpperCase()}
                  </span>
                  <span className="text-sm" style={{ color: "#a0968a" }}>
                    {Math.round(parseFloat(insight.confidence) * 100) || insight.confidence}% confidence
                  </span>
                </div>
                <h3 className="font-semibold mb-2" style={{ color: "#f1ebe2" }}>
                  {insight.headline}
                </h3>
                <p className="text-sm mb-3" style={{ color: "#a0968a" }}>
                  {insight.body}
                </p>
                <span
                  className="text-xs px-3 py-1 rounded-full"
                  style={{
                    background:
                      insight.metric_direction === "positive" ? "rgba(123,200,143,0.1)" : "rgba(248,113,113,0.1)",
                    color: insight.metric_direction === "positive" ? "#7bc88f" : "#f87171",
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
