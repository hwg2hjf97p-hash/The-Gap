"use client";

import { useState } from "react";
import { ArrowUp } from "lucide-react";
import { getUserId } from "../../lib/identity";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";

const SUGGESTED = [
  "Why was my energy low this week?",
  "What's causing my afternoon crashes?",
  "What have you learned about me?",
  "Should I cut caffeine?",
];

type Message = { role: "user" | "assistant"; text: string };

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || asking) return;
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setAsking(true);
    try {
      const uid = getUserId();
      const res = await fetch(`${API_URL}/assistant/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: uid, question: q }),
      });
      const data = await res.json();
      const answer = res.ok
        ? data.answer
        : "I couldn't reach the assistant just now — try again in a moment.";
      setMessages((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Couldn't reach the assistant — check your connection and try again." },
      ]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "#0a1710" }}>
      <div className="max-w-lg mx-auto w-full px-5 py-8 flex-1 flex flex-col">
        {messages.length === 0 ? (
          <>
            <p className="text-xs font-mono tracking-widest mb-3" style={{ color: "#c9a84c" }}>
              YOUR PERSONAL SCIENTIST
            </p>
            <h1 className="text-3xl font-bold mb-6" style={{ color: "#eef3f0" }}>
              Ask anything
            </h1>
            <p className="text-lg mb-8" style={{ color: "#eef3f0" }}>
              I&apos;ve been watching your data. Ask me something.
            </p>
            <div className="space-y-3 mb-8">
              {SUGGESTED.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="w-full flex items-center justify-between rounded-2xl px-5 py-4 text-left"
                  style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
                >
                  <span style={{ color: "#eef3f0" }}>{q}</span>
                  <span style={{ color: "#c9a84c" }}>→</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="flex-1 space-y-4 mb-6 overflow-y-auto">
            {messages.map((m, i) => (
              <div
                key={i}
                className="rounded-2xl px-4 py-3 max-w-[85%]"
                style={{
                  background: m.role === "user" ? "#c9a84c" : "#132c1f",
                  border: m.role === "assistant" ? "1px solid #1a3d2b" : "none",
                  marginLeft: m.role === "user" ? "auto" : 0,
                }}
              >
                <p className="text-sm" style={{ color: m.role === "user" ? "#0a1710" : "#eef3f0" }}>
                  {m.text}
                </p>
              </div>
            ))}
            {asking && (
              <div className="rounded-2xl px-4 py-3 max-w-[85%]" style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>
                <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
              </div>
            )}
          </div>
        )}

        {/* Input */}
        <div
          className="flex items-center gap-3 rounded-2xl px-5 py-3 mt-auto"
          style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(input)}
            placeholder="Ask about your patterns…"
            className="flex-1 bg-transparent outline-none text-sm"
            style={{ color: "#eef3f0" }}
          />
          <button
            onClick={() => ask(input)}
            disabled={!input.trim() || asking}
            className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 disabled:opacity-40"
            style={{ background: "#c9a84c" }}
          >
            <ArrowUp size={18} color="#0a1710" />
          </button>
        </div>
      </div>
    </div>
  );
}
