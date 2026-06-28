"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-production.up.railway.app";

const PROVIDERS = [
  {
    id: "whoop",
    name: "Whoop",
    icon: "⚡",
    description: "HRV, recovery score, sleep stages, strain",
    color: "#ff3c00",
    dataPoints: ["Heart Rate Variability", "Recovery Score", "Deep Sleep", "Strain"],
  },
  {
    id: "oura",
    name: "Oura Ring",
    icon: "💍",
    description: "Readiness, HRV, sleep stages, activity, temperature",
    color: "#6366f1",
    dataPoints: ["Readiness Score", "HRV", "Sleep Efficiency", "Body Temperature"],
  },
  {
    id: "strava",
    name: "Strava",
    icon: "🏃",
    description: "Training load, workout intensity, activity type",
    color: "#fc4c02",
    dataPoints: ["Training Load", "Hard Sessions", "Weekly Volume", "Activity Type"],
  },
  {
    id: "google",
    name: "Google Calendar",
    icon: "📅",
    description: "Meeting load, late meetings, busy-day patterns",
    color: "#34a853",
    dataPoints: ["Meeting Hours", "Late Meetings", "Calendar Density", "Free Days"],
  },
];

function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("gap_user_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("gap_user_id", id);
  }
  return id;
}

function ConnectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [connected, setConnected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const userId = typeof window !== "undefined" ? getUserId() : "";

  useEffect(() => {
    // Handle OAuth callback result
    const success = searchParams.get("success");
    const error = searchParams.get("error");
    const provider = searchParams.get("provider");

    if (success && provider) {
      setToast({ msg: `${provider.charAt(0).toUpperCase() + provider.slice(1)} connected successfully.`, type: "success" });
    } else if (error) {
      setToast({ msg: `Connection failed: ${error}. Please try again.`, type: "error" });
    }

    // Auto-dismiss toast
    if (success || error) {
      setTimeout(() => setToast(null), 4000);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!userId) return;
    fetch(`${API_URL}/connect/status/${userId}`)
      .then((r) => r.json())
      .then((data) => {
        setConnected((data.connected || []).map((c: { provider: string }) => c.provider));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [userId]);

  function handleConnect(provider: string) {
    const url = `${API_URL}/connect/${provider}?user_id=${encodeURIComponent(userId)}`;
    window.location.href = url;
  }

  async function handleDisconnect(provider: string) {
    try {
      await fetch(`${API_URL}/connect/${provider}/${userId}`, { method: "DELETE" });
      setConnected((prev) => prev.filter((p) => p !== provider));
      setToast({ msg: `${provider} disconnected.`, type: "success" });
      setTimeout(() => setToast(null), 3000);
    } catch {
      setToast({ msg: "Could not disconnect. Please try again.", type: "error" });
    }
  }

  async function handleRunAnalysis() {
    router.push(`/results/live?user_id=${userId}`);
  }

  const hasAnyConnected = connected.length > 0;
  const hasHealthSource = connected.includes("whoop") || connected.includes("oura");

  return (
    <div className="min-h-screen px-4 py-16">
      <div className="max-w-2xl mx-auto">

        {/* Toast */}
        {toast && (
          <div
            className="fixed top-6 left-1/2 -translate-x-1/2 px-6 py-3 rounded-xl text-sm font-medium z-50 shadow-lg"
            style={{
              background: toast.type === "success" ? "#132c1f" : "rgba(201,68,68,0.15)",
              color: toast.type === "success" ? "#34d399" : "#f87171",
              border: `1px solid ${toast.type === "success" ? "#1a3d2b" : "rgba(201,68,68,0.3)"}`,
            }}
          >
            {toast.msg}
          </div>
        )}

        {/* Header */}
        <div className="text-center mb-12">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono mb-4"
            style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}
          >
            ✦ Passive mode — connect once, insights update daily
          </div>
          <h1 className="text-4xl font-bold tracking-tight mb-3" style={{ color: "#eef3f0" }}>
            Connect your data sources
          </h1>
          <p style={{ color: "#a2bcaf" }}>
            Connect your devices once. The Gap pulls fresh data every day and
            updates your causal insights automatically — no uploads needed.
          </p>
        </div>

        {/* Provider cards */}
        <div className="space-y-4 mb-8">
          {PROVIDERS.map((provider) => {
            const isConnected = connected.includes(provider.id);
            return (
              <div
                key={provider.id}
                className="rounded-2xl p-6 transition-all"
                style={{
                  background: isConnected ? "#132c1f" : "#0f1f17",
                  border: `1px solid ${isConnected ? "#34d399" : "#1a3d2b"}`,
                }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div
                      className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0"
                      style={{ background: "#0a1710" }}
                    >
                      {provider.icon}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold" style={{ color: "#eef3f0" }}>
                          {provider.name}
                        </h3>
                        {isConnected && (
                          <span
                            className="text-xs px-2 py-0.5 rounded-full"
                            style={{ background: "rgba(52,211,153,0.1)", color: "#34d399" }}
                          >
                            Connected
                          </span>
                        )}
                      </div>
                      <p className="text-sm mb-3" style={{ color: "#a2bcaf" }}>
                        {provider.description}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {provider.dataPoints.map((dp) => (
                          <span
                            key={dp}
                            className="text-xs px-2 py-1 rounded-lg"
                            style={{ background: "#0a1710", color: "#a2bcaf" }}
                          >
                            {dp}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 flex-shrink-0">
                    {isConnected ? (
                      <button
                        onClick={() => handleDisconnect(provider.id)}
                        className="px-4 py-2 rounded-lg text-sm transition-all"
                        style={{
                          background: "transparent",
                          color: "#a2bcaf",
                          border: "1px solid #1a3d2b",
                        }}
                      >
                        Disconnect
                      </button>
                    ) : (
                      <button
                        onClick={() => handleConnect(provider.id)}
                        className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
                        style={{
                          background: "#34d399",
                          color: "#0a1710",
                        }}
                      >
                        Connect →
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Run analysis CTA */}
        {hasHealthSource && (
          <div
            className="rounded-2xl p-6 text-center"
            style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
          >
            <p className="font-medium mb-1" style={{ color: "#eef3f0" }}>
              Ready to analyse
            </p>
            <p className="text-sm mb-4" style={{ color: "#a2bcaf" }}>
              {connected.length} source{connected.length !== 1 ? "s" : ""} connected
              {connected.includes("google") ? " including calendar" : ""} —
              your insights update automatically every morning.
            </p>
            <button
              onClick={handleRunAnalysis}
              className="px-8 py-3 rounded-xl font-semibold text-sm"
              style={{ background: "#34d399", color: "#0a1710" }}
            >
              Run analysis now →
            </button>
          </div>
        )}

        {/* Or upload manually */}
        <div className="mt-6 text-center">
          <p className="text-sm" style={{ color: "#a2bcaf" }}>
            Prefer to upload manually?{" "}
            <a href="/" style={{ color: "#c9a84c" }}>
              Upload a file instead →
            </a>
          </p>
        </div>

      </div>
    </div>
  );
}

export default function ConnectPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
      </div>
    }>
      <ConnectContent />
    </Suspense>
  );
}
