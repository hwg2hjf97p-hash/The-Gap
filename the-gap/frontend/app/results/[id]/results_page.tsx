"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getResults, AnalysisError } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";
import InsightCard from "@/components/InsightCard";
import ShareButton from "@/components/ShareButton";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    // 1. Try sessionStorage first (fresh upload — always works even without Supabase)
    const cached = sessionStorage.getItem("gap_results");
    if (cached) {
      try {
        const parsed = JSON.parse(cached) as AnalysisResponse;
        if (parsed.session_id === id) {
          setData(parsed);
          setLoading(false);
          return;
        }
      } catch {
        // fall through to API
      }
    }

    // 2. Fetch from API (shared link)
    getResults(id)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof AnalysisError) {
          setError(err.message);
        } else {
          setError("Could not load results.");
        }
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div
            className="w-10 h-10 border-2 rounded-full animate-spin mx-auto mb-4"
            style={{ borderColor: "#34d399", borderTopColor: "transparent" }}
          />
          <p style={{ color: "#a2bcaf" }}>Loading your results…</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-4 text-center">
        <div className="text-4xl mb-4">🔍</div>
        <h2 className="text-xl font-semibold mb-2" style={{ color: "#eef3f0" }}>
          Results not found
        </h2>
        <p className="mb-6 max-w-sm" style={{ color: "#a2bcaf" }}>
          {error || "These results may have expired or were opened on a different device."}
        </p>
        <button
          onClick={() => router.push("/")}
          className="px-6 py-3 rounded-xl font-medium text-sm"
          style={{ background: "#34d399", color: "#0a1710" }}
        >
          Run a new analysis
        </button>
      </div>
    );
  }

  const { data_summary, insights } = data;
  const sourceName = data_summary.source === "apple_health" ? "Apple Health" : "Whoop";

  return (
    <div className="min-h-screen px-4 py-16">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="text-center mb-12 animate-fade-in">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono mb-4"
            style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}
          >
            ✦ {insights.length} verified causal pattern{insights.length !== 1 ? "s" : ""} found
          </div>
          <h1 className="text-4xl font-bold tracking-tight mb-3" style={{ color: "#eef3f0" }}>
            Your causal health insights
          </h1>
          <p style={{ color: "#a2bcaf" }}>
            From {data_summary.days} days of {sourceName} data —{" "}
            these are real cause-and-effect patterns, not correlations.
          </p>
        </div>

        {/* Insight cards */}
        <div className="space-y-4">
          {insights.map((insight, i) => (
            <div
              key={insight.hypothesis_id}
              className="animate-slide-up"
              style={{ animationDelay: `${i * 0.08}s`, animationFillMode: "both" }}
            >
              <InsightCard insight={insight} />
            </div>
          ))}
        </div>

        {/* Share + CTA */}
        <div className="mt-12 text-center space-y-4">
          <ShareButton shareUrl={data.share_url} />
          <p className="text-sm" style={{ color: "#a2bcaf" }}>
            Share your insights with anyone
          </p>
          <div className="pt-2">
            <button
              onClick={() => {
                sessionStorage.removeItem("gap_results");
                router.push("/");
              }}
              className="text-sm px-5 py-2 rounded-lg transition-colors"
              style={{
                background: "#132c1f",
                color: "#a2bcaf",
                border: "1px solid #1a3d2b",
              }}
            >
              ← Analyse another export
            </button>
          </div>
        </div>

        {/* Methodology note */}
        <div
          className="mt-16 rounded-xl p-6 text-sm"
          style={{ background: "#132c1f", border: "1px solid #1a3d2b", color: "#a2bcaf" }}
        >
          <p className="font-medium mb-2" style={{ color: "#eef3f0" }}>About these results</p>
          <p>
            The Gap uses Double Machine Learning (LinearDML) from Microsoft&apos;s EconML library — the
            same causal inference framework used by researchers at Microsoft, Uber, and Stanford.
            It controls for confounders (day of week, sleep history, activity levels) to isolate
            genuine cause-and-effect relationships from coincidence.{" "}
            <a
              href="https://econml.azurewebsites.net"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "#c9a84c" }}
            >
              Learn more about EconML →
            </a>
          </p>
        </div>

        {/* Footer CTA */}
        <div className="mt-8 text-center">
          <p className="text-xs" style={{ color: "#a2bcaf" }}>
            causalme.com · Built by Samuel Roberts
          </p>
        </div>
      </div>
    </div>
  );
}
