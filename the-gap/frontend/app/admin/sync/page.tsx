"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";
const SECRET_KEY = "gap_admin_secret";

type Person = { who: string; state: string; fail_count: number; last_error: string; last_ok_minutes_ago: number | null; next_sync_in_minutes: number | null };
type Status = {
  checked_at: string;
  connected_people: number | null;
  queue_table: string;
  queue: { tracked: number; due_now: number; running: number; failing: number; overdue: number; needs_a_look: Person[] } | null;
  server_clock: string;
  error_alerts: string;
  error?: string;
};

const colors = { bg: "#0b1015", panel: "#121a21", border: "rgba(255,255,255,0.1)", text: "#f2f6f8", muted: "#9aa8b2", accent: "#22d3ee", good: "#34e07a", bad: "#ff6b81", warn: "#fbbf24" };
const box: React.CSSProperties = { background: colors.panel, border: `1px solid ${colors.border}`, borderRadius: 14, padding: 18, marginBottom: 16 };
const input: React.CSSProperties = { width: "100%", background: colors.bg, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: 8, padding: "8px 10px", fontSize: 14 };
const button: React.CSSProperties = { background: "transparent", color: colors.accent, border: `1px solid ${colors.accent}`, borderRadius: 999, padding: "8px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer" };

function Tile({ label, value, tone }: { label: string; value: string | number; tone?: "good" | "bad" | "warn" }) {
  const color = tone ? colors[tone] : colors.text;
  return (
    <div style={{ ...box, marginBottom: 0, flex: "1 1 140px" }}>
      <div style={{ color: colors.muted, fontSize: 12, letterSpacing: 1 }}>{label.toUpperCase()}</div>
      <div style={{ color, fontSize: 28, fontWeight: 700, marginTop: 6 }}>{value}</div>
    </div>
  );
}

export default function SyncStatus() {
  const [secret, setSecret] = useState("");
  const [entered, setEntered] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async (key: string) => {
    try {
      const res = await fetch(`${API_URL}/admin/sync/status`, { headers: { "X-Admin-Secret": key }, cache: "no-store" });
      if (res.status === 401) {
        setError("Wrong password.");
        setStatus(null);
        return;
      }
      if (!res.ok) {
        setError(res.status === 404 ? "Not available: the server has no admin password set." : `The server said ${res.status}.`);
        return;
      }
      setStatus(await res.json());
      setError("");
    } catch {
      setError("Couldn't reach the server. It may be waking up: try again in a minute.");
    }
  }, []);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SECRET_KEY) || "";
      if (saved) {
        setSecret(saved);
        load(saved);
      }
    } catch {}
  }, [load]);

  useEffect(() => {
    if (!secret) return;
    const timer = setInterval(() => load(secret), 30000);
    return () => clearInterval(timer);
  }, [secret, load]);

  if (!secret) {
    return (
      <main style={{ background: colors.bg, color: colors.text, minHeight: "100vh", padding: 24, maxWidth: 420, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22 }}>Sync status</h1>
        <p style={{ color: colors.muted, fontSize: 14 }}>Enter the admin password (the same one used for the research review).</p>
        <input type="password" style={input} value={entered} onChange={(e) => setEntered(e.target.value)} placeholder="Admin password" />
        <div style={{ marginTop: 12 }}>
          <button
            style={button}
            onClick={() => {
              try {
                window.localStorage.setItem(SECRET_KEY, entered.trim());
              } catch {}
              setSecret(entered.trim());
              load(entered.trim());
            }}
          >
            Open
          </button>
        </div>
        {error && <p style={{ color: colors.bad }}>{error}</p>}
      </main>
    );
  }

  const q = status?.queue;
  const healthy = !!q && q.overdue === 0 && q.failing === 0;
  return (
    <main style={{ background: colors.bg, color: colors.text, minHeight: "100vh", padding: 24, maxWidth: 760, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>Sync status</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={button} onClick={() => load(secret)}>
            Refresh
          </button>
          <button
            style={{ ...button, color: colors.muted, borderColor: colors.border }}
            onClick={() => {
              try {
                window.localStorage.removeItem(SECRET_KEY);
              } catch {}
              setSecret("");
              setStatus(null);
            }}
          >
            Sign out
          </button>
        </div>
      </div>
      {error && <div style={{ ...box, color: colors.bad }}>{error}</div>}
      {!status && !error && <p style={{ color: colors.muted }}>Loading…</p>}
      {status && (
        <>
          <div style={{ ...box, borderColor: healthy ? colors.good : q ? colors.warn : colors.border }}>
            <strong style={{ color: healthy ? colors.good : colors.warn }}>
              {!q ? "The sync queue isn't set up yet (run phase14.sql)." : healthy ? "Everything is syncing normally." : "Something needs a look."}
            </strong>
            <div style={{ color: colors.muted, fontSize: 13, marginTop: 6 }}>Checked {new Date(status.checked_at).toLocaleTimeString()}. Refreshes by itself every 30 seconds.</div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
            <Tile label="Connected people" value={status.connected_people ?? "?"} />
            <Tile label="Due now" value={q?.due_now ?? "?"} tone={q && q.due_now > 5 ? "warn" : undefined} />
            <Tile label="Running" value={q?.running ?? "?"} />
            <Tile label="Failing" value={q?.failing ?? "?"} tone={q && q.failing > 0 ? "bad" : "good"} />
            <Tile label="Overdue (2h+)" value={q?.overdue ?? "?"} tone={q && q.overdue > 0 ? "bad" : "good"} />
          </div>
          <div style={box}>
            <div>Server clock: <strong style={{ color: status.server_clock === "running" ? colors.good : colors.bad }}>{status.server_clock}</strong></div>
            <div style={{ marginTop: 6 }}>Error alerts (Sentry): <strong style={{ color: status.error_alerts === "on" ? colors.good : colors.warn }}>{status.error_alerts}</strong></div>
          </div>
          {q && q.needs_a_look.length > 0 && (
            <div style={box}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Needs a look</div>
              {q.needs_a_look.map((p) => (
                <div key={p.who} style={{ borderTop: `1px solid ${colors.border}`, padding: "10px 0", fontSize: 14 }}>
                  <strong>{p.who}</strong> <span style={{ color: p.state === "overdue" ? colors.bad : colors.warn }}>{p.state}</span>
                  <div style={{ color: colors.muted, fontSize: 13, marginTop: 4 }}>
                    {p.fail_count > 0 ? `${p.fail_count} failed in a row. ` : ""}
                    {p.last_ok_minutes_ago !== null ? `Last good sync ${p.last_ok_minutes_ago} min ago. ` : "Never synced successfully. "}
                    {p.next_sync_in_minutes !== null ? `Next try ${p.next_sync_in_minutes >= 0 ? `in ${p.next_sync_in_minutes} min` : `${-p.next_sync_in_minutes} min overdue`}.` : ""}
                  </div>
                  {p.last_error && <div style={{ color: colors.bad, fontSize: 13, marginTop: 4 }}>{p.last_error}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
