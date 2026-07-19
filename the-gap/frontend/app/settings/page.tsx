"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Activity, CircleDot, Route, Calendar, LogOut, Cpu, Scale, Watch, Download, Trash2, ChevronRight } from "lucide-react";
import { getUserId, getDisplayName, setDisplayName, resetIdentity } from "../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

const PROVIDERS = [
  { id: "whoop", name: "Whoop", Icon: Activity, color: "#ff3c00" },
  { id: "oura", name: "Oura Ring", Icon: CircleDot, color: "#6366f1" },
  { id: "strava", name: "Strava", Icon: Route, color: "#fc4c02" },
  { id: "google", name: "Google Calendar", Icon: Calendar, color: "#34a853" },
  { id: "withings", name: "Withings", Icon: Scale, color: "#00bcd4" },
  { id: "polar", name: "Polar", Icon: Watch, color: "#e6ff00" },
];

export default function SettingsPage() {
  const router = useRouter();
  const [userId, setUserId] = useState("");
  const [copied, setCopied] = useState(false);
  const [connected, setConnected] = useState<string[]>([]);
  const [nameInput, setNameInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  async function handleExportData() {
    setExporting(true);
    try {
      const res = await fetch(`${API_URL}/account/export/${userId}`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `the-gap-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Export failed — please try again.");
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteAccount() {
    setDeleting(true);
    try {
      await fetch(`${API_URL}/account/${userId}`, { method: "DELETE" });
      resetIdentity();
      router.push("/results/live");
    } catch {
      alert("Deletion failed — please try again.");
      setDeleting(false);
    }
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

        {/* Sync Devices */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            SYNC DEVICES
          </p>
          <div className="rounded-2xl p-4" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <p className="text-xs mb-2" style={{ color: "#a2bcaf" }}>
              This device&apos;s ID — copy this into the mobile app&apos;s Settings to make it use this same account, instead of starting a separate one.
            </p>
            <div className="flex gap-2 mb-3">
              <input
                value={userId}
                readOnly
                className="flex-1 px-3 py-2 rounded-lg bg-transparent outline-none text-xs font-mono"
                style={{ color: "#eef3f0", border: "1px solid #1a3d2b" }}
              />
              <button
                onClick={() => {
                  navigator.clipboard.writeText(userId);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: "#34d399", color: "#0a1710" }}
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <p className="text-xs" style={{ color: "#5c7568" }}>
              No real login system yet — this is a stopgap for keeping one identity across your devices. Anyone with this ID could access this account&apos;s data, so don&apos;t share it publicly.
            </p>
          </div>
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

        {/* Data & Privacy */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            DATA & PRIVACY
          </p>
          <div className="rounded-2xl overflow-hidden" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <button
              onClick={handleExportData}
              disabled={exporting}
              className="w-full flex items-center gap-3 p-4 text-left"
              style={{ borderBottom: "1px solid #1a3d2b" }}
            >
              <Download size={18} color="#c9a84c" />
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                {exporting ? "Preparing your export…" : "Export my data"}
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="w-full flex items-center gap-3 p-4 text-left"
            >
              <Trash2 size={18} color="#f87171" />
              <span className="text-sm flex-1" style={{ color: "#f87171" }}>
                Delete account & data
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </button>
          </div>
        </div>

        {/* Legal */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            LEGAL
          </p>
          <div className="rounded-2xl overflow-hidden" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <a
              href="/privacy"
              className="flex items-center gap-3 p-4"
              style={{ borderBottom: "1px solid #1a3d2b" }}
            >
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                Privacy Policy
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </a>
            <a href="/terms" className="flex items-center gap-3 p-4">
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                Terms of Service
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </a>
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

        {/* Delete confirmation modal */}
        {showDeleteConfirm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center px-4"
            style={{ background: "rgba(0,0,0,0.7)" }}
            onClick={() => setShowDeleteConfirm(false)}
          >
            <div
              className="w-full max-w-sm rounded-2xl p-6"
              style={{ background: "#132c1f", border: "1px solid #3d1a1a" }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-bold mb-2" style={{ color: "#eef3f0" }}>
                Delete everything?
              </h3>
              <p className="text-sm mb-6" style={{ color: "#a2bcaf" }}>
                This permanently deletes all your connections, entries, and
                insights from our servers. This can&apos;t be undone. It doesn&apos;t
                revoke access on the provider&apos;s own side (e.g. Whoop) — do
                that separately there if you want full revocation.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 py-3 rounded-xl text-sm font-medium"
                  style={{ background: "transparent", border: "1px solid #1a3d2b", color: "#a2bcaf" }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleting}
                  className="flex-1 py-3 rounded-xl text-sm font-semibold"
                  style={{ background: "#f87171", color: "#0a1710" }}
                >
                  {deleting ? "Deleting…" : "Delete everything"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Activity, CircleDot, Route, Calendar, LogOut, Cpu, Scale, Watch, Download, Trash2, ChevronRight } from "lucide-react";
import { getUserId, getDisplayName, setDisplayName, resetIdentity } from "../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

const PROVIDERS = [
  { id: "whoop", name: "Whoop", Icon: Activity, color: "#ff3c00" },
  { id: "oura", name: "Oura Ring", Icon: CircleDot, color: "#6366f1" },
  { id: "strava", name: "Strava", Icon: Route, color: "#fc4c02" },
  { id: "google", name: "Google Calendar", Icon: Calendar, color: "#34a853" },
  { id: "withings", name: "Withings", Icon: Scale, color: "#00bcd4" },
  { id: "polar", name: "Polar", Icon: Watch, color: "#e6ff00" },
];

export default function SettingsPage() {
  const router = useRouter();
  const [userId, setUserId] = useState("");
  const [connected, setConnected] = useState<string[]>([]);
  const [nameInput, setNameInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  async function handleExportData() {
    setExporting(true);
    try {
      const res = await fetch(`${API_URL}/account/export/${userId}`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `the-gap-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Export failed — please try again.");
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteAccount() {
    setDeleting(true);
    try {
      await fetch(`${API_URL}/account/${userId}`, { method: "DELETE" });
      resetIdentity();
      router.push("/results/live");
    } catch {
      alert("Deletion failed — please try again.");
      setDeleting(false);
    }
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

        {/* Data & Privacy */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            DATA & PRIVACY
          </p>
          <div className="rounded-2xl overflow-hidden" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <button
              onClick={handleExportData}
              disabled={exporting}
              className="w-full flex items-center gap-3 p-4 text-left"
              style={{ borderBottom: "1px solid #1a3d2b" }}
            >
              <Download size={18} color="#c9a84c" />
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                {exporting ? "Preparing your export…" : "Export my data"}
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="w-full flex items-center gap-3 p-4 text-left"
            >
              <Trash2 size={18} color="#f87171" />
              <span className="text-sm flex-1" style={{ color: "#f87171" }}>
                Delete account & data
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </button>
          </div>
        </div>

        {/* Legal */}
        <div className="mb-8">
          <p className="text-xs font-semibold tracking-wide mb-3" style={{ color: "#a2bcaf" }}>
            LEGAL
          </p>
          <div className="rounded-2xl overflow-hidden" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
            <a
              href="/privacy"
              className="flex items-center gap-3 p-4"
              style={{ borderBottom: "1px solid #1a3d2b" }}
            >
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                Privacy Policy
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </a>
            <a href="/terms" className="flex items-center gap-3 p-4">
              <span className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                Terms of Service
              </span>
              <ChevronRight size={16} color="#5c7568" />
            </a>
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

        {/* Delete confirmation modal */}
        {showDeleteConfirm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center px-4"
            style={{ background: "rgba(0,0,0,0.7)" }}
            onClick={() => setShowDeleteConfirm(false)}
          >
            <div
              className="w-full max-w-sm rounded-2xl p-6"
              style={{ background: "#132c1f", border: "1px solid #3d1a1a" }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-bold mb-2" style={{ color: "#eef3f0" }}>
                Delete everything?
              </h3>
              <p className="text-sm mb-6" style={{ color: "#a2bcaf" }}>
                This permanently deletes all your connections, entries, and
                insights from our servers. This can&apos;t be undone. It doesn&apos;t
                revoke access on the provider&apos;s own side (e.g. Whoop) — do
                that separately there if you want full revocation.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 py-3 rounded-xl text-sm font-medium"
                  style={{ background: "transparent", border: "1px solid #1a3d2b", color: "#a2bcaf" }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleting}
                  className="flex-1 py-3 rounded-xl text-sm font-semibold"
                  style={{ background: "#f87171", color: "#0a1710" }}
                >
                  {deleting ? "Deleting…" : "Delete everything"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
