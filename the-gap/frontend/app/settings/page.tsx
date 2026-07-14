"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Activity, CircleDot, Route, Calendar, LogOut, Cpu, Scale } from "lucide-react";
import { getUserId, getDisplayName, setDisplayName, resetIdentity } from "../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

const PROVIDERS = [
  { id: "whoop", name: "Whoop", Icon: Activity, color: "#ff3c00" },
  { id: "oura", name: "Oura Ring", Icon: CircleDot, color: "#6366f1" },
  { id: "strava", name: "Strava", Icon: Route, color: "#fc4c02" },
  { id: "google", name: "Google Calendar", Icon: Calendar, color: "#34a853" },
  { id: "withings", name: "Withings", Icon: Scale, color: "#00bcd4" },
];

export default function SettingsPage() {
  const router = useRouter();
  const [userId, setUserId] = useState("");
  const [connected, setConnected] = useState<string[]>([]);
  const [nameInput, setNameInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);

  useEffect(() => {
    const id = getUserId();
    setUserId(id);
    setNameInput(getDisplayName());
    loadStatus(id);
  }, []);

  async function loadStatus(uid: string) {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/connect/status/${uid}`);
      const data = await res.json();
      const providerNames = (data.connected ?? []).map((c: { provider: string }) => c.provider);
      setConnected(providerNames);
    } catch {
      setConnected([]);
    } finally {
      setLoading(false);
    }
  }

  function handleConnect(providerId: string) {
    window.location.href = `${API_URL}/connect/${providerId}?user_id=${userId}`;
  }

  async function handleDisconnect(providerId: string) {
    setDisconnecting(providerId);
    try {
      await fetch(`${API_URL}/connect/${providerId}/${userId}`, { method: "DELETE" });
      setConnected((prev) => prev.filter((p) => p !== providerId));
    } finally {
      setDisconnecting(null);
    }
  }

  function saveName() {
    setDisplayName(nameInput);
  }

  function handleSignOut() {
    resetIdentity();
    router.push("/results/live");
  }

  return (
    <div className="min-h-screen" style={{ background: "#0a1710" }}>
      <div className="max-w-lg mx-auto px-5 py-8">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/results/live">
            <ArrowLeft size={22} color="#a2bcaf" />
          </Link>
          <h1 className="text-xl font-bold" style={{ color: "#eef3f0" }}>
            Settings
          </h1>
        </div>

        {/* Profile */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            PROFILE
          </p>
          <div className="rounded-2xl p-4" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <label className="text-xs mb-2 block" style={{ color: "#a2bcaf" }}>
              What should we call you?
            </label>
            <div className="flex gap-2">
              <input
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder="Your name"
                className="flex-1 px-3 py-2 rounded-lg bg-transparent outline-none text-sm"
                style={{ color: "#eef3f0", border: "1px solid #1a3d2b" }}
              />
              <button
                onClick={saveName}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: "#34d399", color: "#0a1710" }}
              >
                Save
              </button>
            </div>
          </div>
        </div>

        {/* Data sources */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            DATA SOURCES
          </p>
          <div className="space-y-3">
            {PROVIDERS.map((p) => {
              const isConnected = connected.includes(p.id);
              return (
                <div
                  key={p.id}
                  className="rounded-2xl p-4 flex items-center gap-4"
                  style={{
                    background: isConnected ? "#132c1f" : "#0f1f17",
                    border: `1px solid ${isConnected ? "#34d399" : "#1a3d2b"}`,
                  }}
                >
                  <div
                    className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: "#0a1710", border: `1px solid ${p.color}33` }}
                  >
                    <p.Icon size={22} color={p.color} />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium" style={{ color: "#eef3f0" }}>
                      {p.name}
                    </p>
                    <p className="text-xs" style={{ color: isConnected ? "#34d399" : "#5c7568" }}>
                      {isConnected ? "Connected" : "Not connected"}
                    </p>
                  </div>
                  {loading ? null : isConnected ? (
                    <button
                      onClick={() => handleDisconnect(p.id)}
                      disabled={disconnecting === p.id}
                      className="text-xs px-3 py-2 rounded-lg font-medium"
                      style={{ color: "#f87171", border: "1px solid #3d1a1a" }}
                    >
                      {disconnecting === p.id ? "…" : "Disconnect"}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleConnect(p.id)}
                      className="text-xs px-3 py-2 rounded-lg font-semibold"
                      style={{ background: "#34d399", color: "#0a1710" }}
                    >
                      Connect
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* About */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            ABOUT
          </p>
          <div
            className="rounded-2xl p-4 flex items-center gap-3"
            style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
          >
            <Cpu size={18} color="#c9a84c" />
            <p className="text-sm" style={{ color: "#a2bcaf" }}>
              The Gap · Causal inference powered by EconML
            </p>
          </div>
        </div>

        {/* Sign out */}
        <button
          onClick={handleSignOut}
          className="w-full flex items-center justify-center gap-2 rounded-2xl py-4 font-semibold"
          style={{ background: "transparent", border: "1px solid #3d1a1a", color: "#f87171" }}
        >
          <LogOut size={18} />
          Sign out
        </button>
        <p className="text-xs text-center mt-3" style={{ color: "#5c7568" }}>
          This clears your local identity on this device — your data on our
          servers isn&apos;t deleted.
        </p>
      </div>
    </div>
  );
}
