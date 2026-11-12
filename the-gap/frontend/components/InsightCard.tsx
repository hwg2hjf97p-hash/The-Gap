"use client";

import { useState } from "react";
import type { Insight } from "@/lib/types";

interface Props {
  insight: Insight;
}

const CONFIDENCE_COLORS = {
  strong:   { dot: "#e0a458", label: "#e0a458" },
  moderate: { dot: "#e0a458", label: "#e0a458" },
  weak:     { dot: "#a0968a", label: "#a0968a" },
};

export default function InsightCard({ insight }: Props) {
  const [expanded, setExpanded] = useState(false);
  const colors = CONFIDENCE_COLORS[insight.confidence];
  const isPositive = insight.metric_direction === "positive";

  // Metric colour: mint for positive, gold for negative (never red)
  const metricColor = isPositive ? "#7bc88f" : "#e0a458";

  return (
    <div
      className="rounded-2xl p-6 transition-all duration-200 cursor-pointer group"
      style={{
        background: "#211d18",
        border: "1px solid #2f2a23",
      }}
      onClick={() => setExpanded((v) => !v)}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-4">
        {/* Left: title + headline */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            {/* Confidence dot */}
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: colors.dot }}
            />
            <span className="text-xs font-medium" style={{ color: colors.label }}>
              {insight.confidence_label}
            </span>
          </div>
          <h3 className="font-semibold text-base mb-1" style={{ color: "#f1ebe2" }}>
            {insight.title}
          </h3>
          <p className="text-sm leading-snug" style={{ color: "#a0968a" }}>
            {insight.headline}
          </p>
        </div>

        {/* Right: metric chip */}
        <div
          className="flex-shrink-0 rounded-xl px-4 py-3 text-center min-w-[80px]"
          style={{ background: "#16130f" }}
        >
          <div className="text-2xl font-bold font-mono" style={{ color: metricColor }}>
            {insight.metric_delta}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "#a0968a" }}>
            {insight.metric_unit}
          </div>
        </div>
      </div>

      {/* Expand toggle */}
      <div className="mt-3 flex items-center gap-1.5">
        <span className="text-xs" style={{ color: "#a0968a" }}>
          {expanded ? "Hide detail" : "See how we know this"}
        </span>
        <span
          className="text-xs transition-transform duration-200"
          style={{
            color: "#a0968a",
            display: "inline-block",
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
          }}
        >
          ▾
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div
          className="mt-4 space-y-4 border-t pt-4"
          style={{ borderColor: "#2f2a23" }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Body */}
          <p className="text-sm leading-relaxed" style={{ color: "#a0968a" }}>
            {insight.body}
          </p>

          {/* Stats row */}
          <div className="flex flex-wrap gap-4 text-xs font-mono"
               style={{ color: "#a0968a" }}>
            <span>
              <span style={{ color: "#f1ebe2" }}>n =</span> {insight.n_observations} days
            </span>
            <span>
              <span style={{ color: "#f1ebe2" }}>ATE =</span>{" "}
              {insight.ate > 0 ? "+" : ""}{insight.ate.toFixed(2)}
            </span>
            <span>
              <span style={{ color: "#f1ebe2" }}>90% CI</span>{" "}
              [{insight.ci_low.toFixed(2)}, {insight.ci_high.toFixed(2)}]
            </span>
          </div>

          {/* Confidence tooltip */}
          <div className="rounded-lg p-3 text-xs"
               style={{ background: "#16130f", color: "#a0968a" }}>
            <span style={{ color: colors.label }}>{insight.confidence_label}: </span>
            {insight.confidence_description}
          </div>

          {/* Actionable tip */}
          {insight.actionable_tip && (
            <div className="rounded-lg p-3 text-sm"
                 style={{ background: "rgba(224,164,88,0.06)", border: "1px solid rgba(224,164,88,0.15)" }}>
              <p className="font-medium mb-0.5" style={{ color: "#e0a458" }}>
                What to do with this
              </p>
              <p style={{ color: "#a0968a" }}>{insight.actionable_tip}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
