"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Settings as SettingsIcon, PenLine, RefreshCw } from "lucide-react";
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

type RawSignal = {
  description: string;
  r: number;
  direction: "positive" | "negative";
  n: number;
  strength_label: "moderate" | "strong";
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
  snapshot?: { latest: SnapshotMetric[]; raw_signals: RawSignal[] };
  experiments?: Experiment[];
  data_period_days?: number;
};

type MetricInfo = {
  label: string;
  explanation: string;
  whyItMatters: string;
  comparisonLabel: string; // e.g. "Typical adult range" or "Whoop's scoring bands"
  comparisonText: string;
  goodDirection: string;
};

const METRIC_INFO: Record<string, MetricInfo> = {
  hrv: {
    label: "Heart Rate Variability",
    explanation:
      "The variation in time between each heartbeat — not your heart rate itself, but how much it naturally speeds up and slows down moment to moment.",
    whyItMatters:
      "Higher HRV generally means your nervous system is well-rested and able to adapt to stress. It tends to drop after poor sleep, illness, alcohol, or high stress, and recover as your body bounces back.",
    comparisonLabel: "Typical adult range",
    comparisonText:
      "20–80ms is common, but this varies hugely by age, fitness, and genetics — there's no single 'normal' number. What matters most is your own trend over time, not comparing to someone else's.",
    goodDirection: "Higher is generally better",
  },
  resting_hr: {
    label: "Resting Heart Rate",
    explanation:
      "How many times your heart beats per minute while you're fully at rest, usually measured overnight.",
    whyItMatters:
      "A lower resting heart rate often reflects better cardiovascular fitness. It tends to rise temporarily with stress, illness, dehydration, or poor sleep.",
    comparisonLabel: "Typical adult range",
    comparisonText:
      "60–100 bpm is considered typical for adults; well-trained athletes often sit lower, around 40–60 bpm.",
    goodDirection: "Lower is generally better",
  },
  sleep_total_min: {
    label: "Sleep Duration",
    explanation: "Total time spent asleep, not counting time lying awake in bed.",
    whyItMatters:
      "Sleep is when most physical recovery happens. Consistently falling short of your body's need shows up in worse next-day HRV, mood, and focus.",
    comparisonLabel: "General guidance",
    comparisonText: "7–9 hours per night is the commonly recommended range for adults.",
    goodDirection: "More (within reason) is generally better",
  },
  recovery_score: {
    label: "Recovery Score",
    explanation:
      "Whoop's own 0–100 score estimating how ready your body is to take on strain today, based on your HRV, resting heart rate, and sleep.",
    whyItMatters:
      "It's a proprietary composite, not an independent medical measurement — think of it as Whoop's summary judgment, useful for spotting your own patterns over time.",
    comparisonLabel: "Whoop's scoring bands",
    comparisonText: "0–33 is considered low, 34–66 medium, 67–100 high, per Whoop's own scoring system.",
    goodDirection: "Higher is generally better",
  },
  sleep_score: {
    label: "Sleep Performance",
    explanation:
      "Whoop's estimate of the percentage of your body's actual sleep need that you got last night.",
    whyItMatters:
      "A proprietary score, not an independent measurement — 100% means you got as much sleep as Whoop estimates your body needed, not necessarily a 'perfect' night.",
    comparisonLabel: "Whoop's scoring bands",
    comparisonText: "Whoop generally treats 70%+ as adequate, with higher being better toward 100%.",
    goodDirection: "Higher is generally better",
  },
  steps: {
    label: "Steps",
    explanation: "Total steps walked or run during the day, from your connected device.",
    whyItMatters:
      "General daily movement is linked to better mood, energy, and cardiovascular health independent of formal exercise.",
    comparisonLabel: "General guidance",
    comparisonText: "7,000–10,000 steps/day is a commonly cited general target for adults.",
    goodDirection: "More is generally better",
  },
  weight_kg: {
    label: "Weight",
    explanation: "Your most recent body weight reading, from a connected smart scale.",
    whyItMatters:
      "Useful mainly as a trend over weeks or months — day-to-day changes are usually water weight, not fat or muscle change, so a single reading rarely means much on its own.",
    comparisonLabel: "A note on this one",
    comparisonText:
      "There's no single 'right' weight — it depends entirely on your height, frame, and goals. This app tracks it purely to look for patterns against your other metrics, not to judge the number itself.",
    goodDirection: "Neither direction is inherently 'better'",
  },
};

function MetricInfoModal({ metric, value, unit, onClose }: { metric: SnapshotMetric; value: number; unit: string; onClose: () => void }) {
  const info = METRIC_INFO[metric.metric];
  if (!info) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center px-0 sm:px-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 max-h-[85vh] overflow-y-auto"
        style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold" style={{ color: "#eef3f0" }}>
            {info.label}
          </h3>
          <button onClick={onClose} className="text-2xl leading-none" style={{ color: "#a2bcaf" }}>
            ×
          </button>
        </div>

        <div className="flex items-baseline gap-2 mb-6">
          <span className="text-4xl font-bold" style={{ color: "#eef3f0" }}>
            {value}
          </span>
          <span className="text-sm" style={{ color: "#a2bcaf" }}>
            {unit} · your latest reading
          </span>
        </div>

        <div className="mb-5">
          <p className="text-xs font-semibold tracking-wide mb-2" style={{ color: "#c9a84c" }}>
            WHAT IT IS
          </p>
          <p className="text-sm" style={{ color: "#eef3f0" }}>
            {info.explanation}
          </p>
        </div>

        <div className="mb-5">
          <p className="text-xs font-semibold tracking-wide mb-2" style={{ color: "#c9a84c" }}>
            WHY IT MATTERS
          </p>
          <p className="text-sm" style={{ color: "#eef3f0" }}>
            {info.whyItMatters}
          </p>
        </div>

        <div className="rounded-2xl p-4" style={{ background: "#0f1f17", border: "1px solid #1a3d2b" }}>
          <p className="text-xs font-semibold tracking-wide mb-2" style={{ color: "#a2bcaf" }}>
            {info.comparisonLabel.toUpperCase()}
          </p>
          <p className="text-sm mb-2" style={{ color: "#eef3f0" }}>
            {info.comparisonText}
          </p>
          <p className="text-xs" style={{ color: "#5c7568" }}>
            {info.goodDirection} — but your own trend over time matters more than any single reading.
          </p>
        </div>
      </div>
    </div>
  );
}

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

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [userId, setUserId] = useState("");
  const [displayName, setDisplayNameState] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [hasAnyConnection, setHasAnyConnection] = useState<boolean | null>(null);
  const [results, setResults] = useState<LatestResults | null>(null);
  const [weekCount, setWeekCount] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [selectedMetric, setSelectedMetric] = useState<SnapshotMetric | null>(null);

  useEffect(() => {
    const id = getUserId();
    setUserId(id);
    setDisplayNameState(getDisplayName());

    const success = searchParams.get("success");
    const provider = searchParams.get("provider");
    const error = searchParams.get("error");

    if (success && provider) {
      setToast(`${provider.charAt(0).toUpperCase() + provider.slice(1)} connected — running your analysis…`);
      router.replace("/results/live");
      loadDashboard(id, /* forceRefresh */ true);
      setTimeout(() => setToast(null), 4000);
    } else if (error) {
      setToast(`Connection failed: ${error}. Please try again.`);
      router.replace("/results/live");
      loadDashboard(id, false);
      setTimeout(() => setToast(null), 4000);
    } else {
      loadDashboard(id, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadDashboard(uid: string, forceRefresh: boolean) {
    setLoading(true);
    try {
      const statusRes = await fetch(`${API_URL}/connect/status/${uid}`);
      const statusData = await statusRes.json();
      const connectedCount = (statusData.connected ?? []).length;
      setHasAnyConnection(connectedCount > 0);

      if (connectedCount > 0 && forceRefresh) {
        // Actually run the analysis — a GET of "latest" alone would just
        // return whatever was last saved, which may be stale or nonexistent.
        setRefreshing(true);
        try {
          await fetch(`${API_URL}/sync/user/${uid}`, { method: "POST" });
        } catch {
          // fall through — we'll still show whatever's already saved
        } finally {
          setRefreshing(false);
        }
      }

      const [resultsRes, weekRes] = await Promise.all([
        fetch(`${API_URL}/results/latest/${uid}`),
        fetch(`${API_URL}/journal/${uid}/week`),
      ]);
      setResults(await resultsRes.json());
      const weekData = await weekRes.json();
      setWeekCount(weekData.count ?? 0);
    } catch {
      setHasAnyConnection(false);
    } finally {
      setLoading(false);
    }
  }

  async function handleManualRefresh() {
    if (!userId || refreshing) return;
    await loadDashboard(userId, true);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a1710" }}>
        <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
      </div>
    );
  }

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
          <p className="text-sm mt-4">
            <a href="/upload" style={{ color: "#c9a84c" }}>
              Or analyse a file you already have →
            </a>
          </p>
        </div>
      </div>
    );
  }

  const insightsCount = results?.insights?.length ?? 0;
  const experiments = results?.experiments ?? [];
  const metrics = results?.snapshot?.latest ?? [];
  const rawSignals = results?.snapshot?.raw_signals ?? [];

  return (
    <div className="min-h-screen" style={{ background: "#0a1710" }}>
      {toast && (
        <div
          className="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl text-sm max-w-[90%] text-center"
          style={{ background: "#132c1f", border: "1px solid #34d399", color: "#eef3f0" }}
        >
          {toast}
        </div>
      )}
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
          <div className="flex items-center gap-2">
            <button
              onClick={handleManualRefresh}
              disabled={refreshing}
              className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
              title="Refresh insights"
            >
              <RefreshCw size={18} color="#a2bcaf" className={refreshing ? "animate-spin" : ""} />
            </button>
            <Link
              href="/settings"
              className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
            >
              <SettingsIcon size={20} color="#a2bcaf" />
            </Link>
          </div>
        </div>

        {refreshing && (
          <p className="text-xs text-center mb-4" style={{ color: "#a2bcaf" }}>
            Running your analysis — this can take up to a minute…
          </p>
        )}

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
              const hasInfo = !!METRIC_INFO[m.metric];
              return (
                <button
                  key={m.metric}
                  onClick={() => hasInfo && setSelectedMetric(m)}
                  className="rounded-2xl p-4 text-left"
                  style={{
                    background: "#132c1f",
                    border: "1px solid #1a3d2b",
                    cursor: hasInfo ? "pointer" : "default",
                  }}
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
                    {hasInfo && <span style={{ color: "#5c7568" }}> · tap for details</span>}
                  </p>
                  <Sparkline values={m.recent} color={color} />
                </button>
              );
            })}
          </div>
        )}

        {/* Raw patterns we're watching (restored) */}
        {rawSignals.length > 0 && (
          <div
            className="rounded-2xl p-4 mb-6"
            style={{ background: "#0f1f17", border: "1px dashed #2a4d3a" }}
          >
            <p className="text-xs mb-3" style={{ color: "#a2bcaf" }}>
              Raw patterns we&apos;re watching — not yet causally tested (needs 30+ days for that)
            </p>
            <div className="space-y-2">
              {rawSignals.map((s, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span style={{ color: "#eef3f0" }}>{s.description}</span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full flex-shrink-0 ml-2"
                    style={{ background: "rgba(201,168,76,0.1)", color: "#c9a84c" }}
                  >
                    {s.strength_label} {s.direction === "positive" ? "+" : "−"}
                    {Math.abs(s.r)} (n={s.n})
                  </span>
                </div>
              ))}
            </div>
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

      {selectedMetric && (
        <MetricInfoModal
          metric={selectedMetric}
          value={selectedMetric.value}
          unit={selectedMetric.unit}
          onClose={() => setSelectedMetric(null)}
        />
      )}
    </div>
  );
}

export default function HomeDashboard() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a1710" }}>
          <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
        </div>
      }
    >
      <HomeContent />
    </Suspense>
  );
}
