"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Settings as SettingsIcon, PenLine } from "lucide-react";
import { getUserId, getDisplayName } from "../../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

type SnapshotMetric = {
  metric: string;
  label: string;
  value: number;
  unit: string;
  trend: "up" | "down" | "flat";
  is_improving: boolean | null;
  recent: number[];
};

type Experiment = {
  id: string;
  treatment_label: string;
  outcome_label: string;
  category: string;
  current: number;
  required: number;
};

type LatestResults = {
  found: boolean;
  insights?: unknown[];
  snapshot?: { latest: SnapshotMetric[]; raw_signals: unknown[] };
  experiments?: Experiment[];
  data_period_days?: number;
};

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (!values || values.length < 2) {
    return <div style={{ height: 32 }} />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 100;
  const h = 32;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 32 }} preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function HomeDashboard() {
  const [userId, setUserId] = useState("");
  const [displayName, setDisplayNameState] = useState("");
  const [loading, setLoading] = useState(true);
  const [hasAnyConnection, setHasAnyConnection] = useState<boolean | null>(null);
  const [results, setResults] = useState<LatestResults | null>(null);
  const [weekCount, setWeekCount] = useState(0);

  useEffect(() => {
    const id = getUserId();
    setUserId(id);
    setDisplayNameState(getDisplayName());
    loadDashboard(id);
  }, []);

  async function loadDashboard(uid: string) {
    setLoading(true);
    try {
      const [statusRes, resultsRes, weekRes] = await Promise.all([
        fetch(`${API_URL}/connect/status/${uid}`),
        fetch(`${API_URL}/results/latest/${uid}`),
        fetch(`${API_URL}/journal/${uid}/week`),
      ]);
      const statusData = await statusRes.json();
      const resultsData = await resultsRes.json();
      const weekData = await weekRes.json();

      setHasAnyConnection((statusData.connected ?? []).length > 0);
      setResults(resultsData);
      setWeekCount(weekData.count ?? 0);
    } catch {
      setHasAnyConnection(false);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a1710" }}>
        <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
      </div>
    );
  }

  // Onboarding state — nothing connected yet
  if (!hasAnyConnection) {
    return (
      <div className="min-h-screen px-5 py-10" style={{ background: "#0a1710" }}>
        <div className="max-w-lg mx-auto text-center pt-16">
          <p className="text-xs font-mono tracking-widest mb-3" style={{ color: "#c9a84c" }}>
            PERSONAL CAUSAL INTELLIGENCE
          </p>
          <h1 className="text-3xl font-bold mb-3" style={{ color: "#eef3f0" }}>
            Let&apos;s connect your first data source
          </h1>
          <p className="text-sm mb-8" style={{ color: "#a2bcaf" }}>
            Your dashboard fills in automatically once something&apos;s connected —
            Whoop, Oura, or your calendar all work.
          </p>
          <Link
            href="/settings"
            className="inline-block px-8 py-3 rounded-xl font-semibold text-sm"
            style={{ background: "#34d399", color: "#0a1710" }}
          >
            Connect a data source →
          </Link>
        </div>
      </div>
    );
  }

  const insightsCount = results?.insights?.length ?? 0;
  const experiments = results?.experiments ?? [];
  const metrics = results?.snapshot?.latest ?? [];

  return (
    <div className="min-h-screen" style={{ background: "#0a1710" }}>
      <div className="max-w-lg mx-auto px-5 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-sm" style={{ color: "#a2bcaf" }}>
              {greeting()},
            </p>
            <h1 className="text-3xl font-bold" style={{ color: "#eef3f0" }}>
              {displayName || "there"}
            </h1>
          </div>
          <Link
            href="/settings"
            className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0"
            style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
          >
            <SettingsIcon size={20} color="#a2bcaf" />
          </Link>
        </div>

        {/* Weekly stats strip */}
        <div className="rounded-2xl p-5 mb-6" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
          <p className="text-xs font-mono tracking-widest mb-4" style={{ color: "#c9a84c" }}>
            THIS WEEK
          </p>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="text-2xl font-bold" style={{ color: "#eef3f0" }}>
                {experiments.length}
              </p>
              <p className="text-xs mt-1" style={{ color: "#a2bcaf" }}>
                Experiments running
              </p>
            </div>
            <div style={{ borderLeft: "1px solid #1a3d2b", borderRight: "1px solid #1a3d2b" }}>
              <p className="text-2xl font-bold" style={{ color: "#eef3f0" }}>
                {insightsCount}
              </p>
              <p className="text-xs mt-1" style={{ color: "#a2bcaf" }}>
                Insights discovered
              </p>
            </div>
            <div>
              <p className="text-2xl font-bold" style={{ color: "#eef3f0" }}>
                {weekCount}
              </p>
              <p className="text-xs mt-1" style={{ color: "#a2bcaf" }}>
                Quick entries logged
              </p>
            </div>
          </div>
        </div>

        {/* Metric grid with sparklines */}
        {metrics.length > 0 && (
          <div className="grid grid-cols-2 gap-3 mb-6">
            {metrics.map((m) => {
              const color =
                m.is_improving === null ? "#c9a84c" : m.is_improving ? "#34d399" : "#f87171";
              return (
                <div
                  key={m.metric}
                  className="rounded-2xl p-4"
                  style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
                >
                  <div className="flex items-baseline gap-1 mb-1">
                    <span className="text-2xl font-bold" style={{ color: "#eef3f0" }}>
                      {m.value}
                    </span>
                    <span className="text-xs" style={{ color: "#a2bcaf" }}>
                      {m.unit}
                    </span>
                  </div>
                  <p className="text-xs mb-2" style={{ color: "#a2bcaf" }}>
                    {m.label}
                  </p>
                  <Sparkline values={m.recent} color={color} />
                </div>
              );
            })}
          </div>
        )}

        {/* Quick Entry CTA */}
        <Link
          href="/journal"
          className="flex items-center gap-4 rounded-2xl p-5 mb-8"
          style={{ background: "#c9a84c" }}
        >
          <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "#0a1710" }}>
            <PenLine size={20} color="#c9a84c" />
          </div>
          <div className="flex-1">
            <p className="font-semibold" style={{ color: "#0a1710" }}>
              Quick Entry
            </p>
            <p className="text-sm" style={{ color: "#2a2410" }}>
              Log a moment — it feeds straight into your insights
            </p>
          </div>
          <span className="text-xl" style={{ color: "#0a1710" }}>→</span>
        </Link>

        {/* Running on you */}
        {experiments.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold" style={{ color: "#eef3f0" }}>
                Running on you
              </h3>
              <Link href="/insights" className="text-sm font-medium" style={{ color: "#c9a84c" }}>
                View all
              </Link>
            </div>
            <div className="space-y-3">
              {experiments.slice(0, 3).map((e) => {
                const pct = Math.min(100, Math.round((e.current / e.required) * 100));
                return (
                  <div
                    key={e.id}
                    className="rounded-2xl p-4"
                    style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
                  >
                    <p className="font-medium mb-3" style={{ color: "#eef3f0" }}>
                      {e.treatment_label} → {e.outcome_label}
                    </p>
                    <div className="w-full rounded-full h-1.5 mb-2" style={{ background: "#1a3d2b" }}>
                      <div
                        className="h-1.5 rounded-full"
                        style={{ width: `${pct}%`, background: "#c9a84c" }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs" style={{ color: "#a2bcaf" }}>
                      <span>Day {e.current} of {e.required}</span>
                      <span>Gathering data</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
