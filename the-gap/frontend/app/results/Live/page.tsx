"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://the-gap-production.up.railway.app";

function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("gap_user_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("gap_user_id", id);
  }
  return id;
}

const STEPS = [
  "Fetching your Whoop data…",
  "Reading sleep & HRV records…",
  "Running causal analysis…",
  "Mapping cause-and-effect patterns…",
  "Almost there…",
];

function LiveSyncContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const hasRun = useRef(false);

  const userId =
    searchParams.get("user_id") ||
    (typeof window !== "undefined" ? getUserId() : "");

  // Cycle through status messages while waiting
  useEffect(() => {
    const interval = setInterval(() => {
      setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!userId || hasRun.current) return;
    hasRun.current = true;

    async function runSync() {
      try {
        const resp = await fetch(`${API_URL}/sync/user/${userId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          const msg =
            data.detail ||
            "Analysis failed. Please check your device is synced and try again.";
          setError(msg);
          return;
        }

        const data = await resp.json();
        const sessionId = data.session_id;

        if (!sessionId) {
          setError("No results returned. Please try again.");
          return;
        }

        router.replace(`/results/${sessionId}`);
      } catch (err) {
        setError(
          "Could not reach the server. Check your internet connection and try again."
        );
      }
    }

    runSync();
  }, [userId, router]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div
          className="max-w-md w-full rounded-2xl p-8 text-center"
          style={{ background: "#0f1f17", border: "1px solid #1a3d2b" }}
        >
          <div className="text-4xl mb-4">⚠️</div>
          <h2
            className="text-xl font-semibold mb-3"
            style={{ color: "#eef3f0" }}
          >
            Something went wrong
          </h2>
          <p className="text-sm mb-6" style={{ color: "#a2bcaf" }}>
            {error}
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => {
                hasRun.current = false;
                setError(null);
                setStepIndex(0);
                // Re-trigger sync
                const event = new Event("retry");
                window.dispatchEvent(event);
              }}
              className="px-5 py-2 rounded-xl text-sm font-medium"
              style={{ background: "#34d399", color: "#0a1710" }}
            >
              Try again
            </button>
            <button
              onClick={() => router.push("/connect")}
              className="px-5 py-2 rounded-xl text-sm"
              style={{
                background: "transparent",
                color: "#a2bcaf",
                border: "1px solid #1a3d2b",
              }}
            >
              Back to connect
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-sm w-full text-center">
        {/* Spinner */}
        <div className="flex justify-center mb-8">
          <div
            className="w-16 h-16 rounded-full border-4 animate-spin"
            style={{
              borderColor: "#1a3d2b",
              borderTopColor: "#34d399",
            }}
          />
        </div>

        {/* Heading */}
        <h2
          className="text-2xl font-bold mb-2"
          style={{ color: "#eef3f0" }}
        >
          Analysing your data
        </h2>

        {/* Animated step */}
        <p
          key={stepIndex}
          className="text-sm transition-all"
          style={{ color: "#a2bcaf" }}
        >
          {STEPS[stepIndex]}
        </p>

        {/* Progress dots */}
        <div className="flex justify-center gap-2 mt-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-full transition-all duration-500"
              style={{
                background: i <= stepIndex ? "#34d399" : "#1a3d2b",
                transform: i === stepIndex ? "scale(1.3)" : "scale(1)",
              }}
            />
          ))}
        </div>

        <p className="text-xs mt-6" style={{ color: "#4a6858" }}>
          This usually takes 15–30 seconds
        </p>
      </div>
    </div>
  );
}

export default function LiveResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a1710" }}>
          <div
            className="w-8 h-8 border-2 rounded-full animate-spin"
            style={{
              borderColor: "#34d399",
              borderTopColor: "transparent",
            }}
          />
        </div>
      }
    >
      <LiveSyncContent />
    </Suspense>
  );
}

// Force dynamic rendering — prevents static generation errors with useSearchParams
export const dynamic = "force-dynamic";
