"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "https://the-gap-backend.onrender.com";
const MAX_LENGTH = 280;

type ExtractedDay = {
  entry_date: string;
  entry_count: number;
  mood_score: number | null;
  stress_event: number | null;
  travel_event: number | null;
  illness_event: number | null;
  conflict_event: number | null;
  big_win_event: number | null;
  summary: string;
};

function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("gap_user_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("gap_user_id", id);
  }
  return id;
}

type Entry = {
  id: string;
  entry_text: string;
  created_at: string;
};

const PROMPTS = [
  "What just happened?",
  "Anything worth remembering from the last hour?",
  "How's the day going right now?",
  "Something small you'd otherwise forget?",
];

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const mins = Math.round((now - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return `${hrs}h ago`;
}

export default function JournalPage() {
  const [userId, setUserId] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [extracted, setExtracted] = useState<ExtractedDay[]>([]);
  const [showExtracted, setShowExtracted] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [streak, setStreak] = useState(0);
  const [prompt] = useState(() => PROMPTS[Math.floor(Math.random() * PROMPTS.length)]);
  const [justLogged, setJustLogged] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const id = getUserId();
    setUserId(id);
    loadToday(id);
  }, []);

  async function loadToday(uid: string) {
    try {
      const [entriesRes, streakRes, extractedRes] = await Promise.all([
        fetch(`${API_URL}/journal/${uid}/today`),
        fetch(`${API_URL}/journal/${uid}/streak`),
        fetch(`${API_URL}/journal/${uid}/extracted?days=30`),
      ]);
      const entriesData = await entriesRes.json();
      const streakData = await streakRes.json();
      const extractedData = await extractedRes.json();
      setEntries(entriesData.entries ?? []);
      setStreak(streakData.streak ?? 0);
      setExtracted(extractedData.days ?? []);
    } catch {
      // silent — an empty list is a fine fallback here
    }
  }

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setSending(true);
    try {
      const res = await fetch(`${API_URL}/journal/entry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, text: trimmed }),
      });
      if (res.ok) {
        const data = await res.json();
        setStreak(data.streak ?? streak);
        setEntries((prev) => [
          ...prev,
          { id: `local-${Date.now()}`, entry_text: trimmed, created_at: new Date().toISOString() },
        ]);
        setText("");
        setJustLogged(true);
        setTimeout(() => setJustLogged(false), 1800);
        inputRef.current?.focus();
      }
    } catch {
      // no-op — the input text stays so nothing is lost, user can just hit send again
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const remaining = MAX_LENGTH - text.length;

  return (
    <div className="min-h-screen" style={{ background: "#0a1710" }}>
      <div className="max-w-lg mx-auto px-5 py-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <Link href="/results/live" className="text-sm" style={{ color: "#a2bcaf" }}>
            ← Back
          </Link>
          {streak > 0 && (
            <div
              className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-mono"
              style={{ background: "#132c1f", color: "#c9a84c", border: "1px solid #1a3d2b" }}
            >
              🔥 {streak} day{streak !== 1 ? "s" : ""}
            </div>
          )}
        </div>

        <h1 className="text-3xl font-bold tracking-tight mb-2" style={{ color: "#eef3f0" }}>
          Quick Entry
        </h1>
        <p className="text-sm mb-8" style={{ color: "#a2bcaf" }}>
          Not a journal — just moments. Log the small stuff as it happens; a few
          words is plenty. The more you log, the more The Gap has to work with.
        </p>

        {/* Input box */}
        <div
          className="rounded-2xl p-4 mb-6"
          style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
        >
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_LENGTH))}
            onKeyDown={handleKeyDown}
            placeholder={prompt}
            rows={2}
            className="w-full bg-transparent resize-none outline-none text-base"
            style={{ color: "#eef3f0" }}
            autoFocus
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs" style={{ color: remaining < 30 ? "#f87171" : "#a2bcaf" }}>
              {remaining} left
            </span>
            <button
              onClick={handleSend}
              disabled={!text.trim() || sending}
              className="px-5 py-2 rounded-xl font-semibold text-sm disabled:opacity-40"
              style={{ background: "#34d399", color: "#0a1710" }}
            >
              {sending ? "Logging…" : "Log it →"}
            </button>
          </div>
        </div>

        {justLogged && (
          <p className="text-xs text-center mb-6" style={{ color: "#34d399" }}>
            Got it — logged. Anything else on your mind?
          </p>
        )}

        {/* Today's entries */}
        <div>
          <h3 className="text-xs font-semibold mb-3 tracking-wide" style={{ color: "#a2bcaf" }}>
            TODAY — {entries.length} moment{entries.length !== 1 ? "s" : ""} logged
          </h3>

          {entries.length === 0 ? (
            <p className="text-sm" style={{ color: "#5c7568" }}>
              Nothing logged yet today. First one's the hardest — just a sentence is enough.
            </p>
          ) : (
            <div className="space-y-2">
              {[...entries].reverse().map((e) => (
                <div
                  key={e.id}
                  className="rounded-xl px-4 py-3 flex items-start justify-between gap-3"
                  style={{ background: "#0f1f17", border: "1px solid #1a3d2b" }}
                >
                  <p className="text-sm flex-1" style={{ color: "#eef3f0" }}>
                    {e.entry_text}
                  </p>
                  <span className="text-xs flex-shrink-0" style={{ color: "#5c7568" }}>
                    {timeAgo(e.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* What Claude extracted */}
        {extracted.length > 0 && (
          <div className="mt-10">
            <button
              onClick={() => setShowExtracted((s) => !s)}
              className="w-full flex items-center justify-between text-xs font-semibold mb-3 tracking-wide"
              style={{ color: "#a2bcaf" }}
            >
              <span>WHAT CLAUDE EXTRACTED ({extracted.length} day{extracted.length !== 1 ? "s" : ""})</span>
              <span>{showExtracted ? "▲" : "▼"}</span>
            </button>

            {showExtracted && (
              <div className="space-y-2">
                {extracted.map((d) => {
                  const flags = [
                    d.stress_event ? "stress" : null,
                    d.travel_event ? "travel" : null,
                    d.illness_event ? "illness" : null,
                    d.conflict_event ? "conflict" : null,
                    d.big_win_event ? "big win" : null,
                  ].filter(Boolean) as string[];

                  return (
                    <div
                      key={d.entry_date}
                      className="rounded-xl px-4 py-3"
                      style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-mono" style={{ color: "#a2bcaf" }}>
                          {d.entry_date} · {d.entry_count} entr{d.entry_count !== 1 ? "ies" : "y"}
                        </span>
                        {d.mood_score !== null && (
                          <span
                            className="text-xs px-2 py-0.5 rounded-full"
                            style={{
                              background:
                                d.mood_score > 0.15
                                  ? "rgba(52,211,153,0.1)"
                                  : d.mood_score < -0.15
                                  ? "rgba(248,113,113,0.1)"
                                  : "rgba(162,188,175,0.1)",
                              color:
                                d.mood_score > 0.15
                                  ? "#34d399"
                                  : d.mood_score < -0.15
                                  ? "#f87171"
                                  : "#a2bcaf",
                            }}
                          >
                            mood {d.mood_score > 0 ? "+" : ""}
                            {d.mood_score.toFixed(2)}
                          </span>
                        )}
                      </div>
                      <p className="text-sm mb-2" style={{ color: "#eef3f0" }}>
                        {d.summary || "—"}
                      </p>
                      {flags.length > 0 && (
                        <div className="flex gap-1 flex-wrap">
                          {flags.map((f) => (
                            <span
                              key={f}
                              className="text-xs px-2 py-0.5 rounded-full"
                              style={{ background: "rgba(201,168,76,0.1)", color: "#c9a84c" }}
                            >
                              {f}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
