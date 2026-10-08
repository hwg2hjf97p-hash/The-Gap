"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://the-gap-backend.onrender.com";
const SECRET_KEY = "gap_admin_secret";
const CATEGORIES = [
  ["sleep", "Sleep"],
  ["body", "Body"],
  ["fitness", "Fitness"],
  ["recovery", "Recovery"],
  ["stress_mood", "Stress & Mood"],
  ["habits", "Habits"],
] as const;

type Checks = {
  doi_ok?: boolean;
  title_match?: boolean;
  numbers_ok?: boolean;
  wording_ok?: boolean;
  unsupported_numbers?: string[];
  abstract_numbers?: string[];
  banned_found?: string[];
  problems?: string[];
};

type Card = {
  id: string;
  category: string;
  title: string;
  plain_summary: string;
  finding: string;
  population: string | null;
  sample_size: number | null;
  study_type: string;
  year: number | null;
  journal: string | null;
  doi: string | null;
  pubmed_id: string | null;
  url: string;
  caution_notes: string | null;
  experiment_label: string | null;
  metric_tags: string[];
  weight_related: boolean;
  verified: boolean;
  can_approve: boolean;
  blocking_problems: string[];
  mentions_medication?: string[];
  source: { pubmed_title: string | null; abstract: string | null; checks: Checks };
};

type Stats = {
  by_category: Record<string, { approved: number; pending: number; rejected: number }>;
  totals: { approved: number; pending: number; rejected: number };
  seed: { running: boolean; current_topic: string; topics_total: number; topics_done: number; added: number; skipped: number; errors: string[] };
};

const colors = { bg: "#0b1015", panel: "#121a21", border: "rgba(255,255,255,0.1)", text: "#f2f6f8", muted: "#9aa8b2", accent: "#22d3ee", good: "#34e07a", bad: "#ff6b81" };

const box: React.CSSProperties = { background: colors.panel, border: `1px solid ${colors.border}`, borderRadius: 14, padding: 18, marginBottom: 16 };
const input: React.CSSProperties = { width: "100%", background: colors.bg, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: 8, padding: "8px 10px", fontSize: 14, fontFamily: "inherit" };
const button: React.CSSProperties = { background: "transparent", color: colors.accent, border: `1px solid ${colors.accent}`, borderRadius: 999, padding: "8px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer" };

export default function EvidenceReview() {
  const [secret, setSecret] = useState("");
  const [entered, setEntered] = useState("");
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const [cards, setCards] = useState<Card[]>([]);
  const [seedCategory, setSeedCategory] = useState("");
  const [perTopic, setPerTopic] = useState(2);

  const call = useCallback(
    async (path: string, init: RequestInit = {}) => {
      const res = await fetch(`${API_URL}/admin/evidence${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", "X-Admin-Secret": secret, ...(init.headers || {}) },
      });
      const body = await res.json().catch(() => ({}));
      return { ok: res.ok, status: res.status, body };
    },
    [secret]
  );

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(SECRET_KEY);
      if (saved) setSecret(saved);
    } catch {}
  }, []);

  const loadStats = useCallback(async () => {
    const r = await call("/stats");
    if (r.status === 401 || r.status === 404) {
      setAuthed(false);
      setError(r.status === 404 ? "The review tool isn't switched on yet (ADMIN_SECRET isn't set on the server)." : "Wrong password.");
      return false;
    }
    if (r.ok) {
      setStats(r.body);
      setAuthed(true);
      setError("");
      return true;
    }
    setError("Couldn't reach the server.");
    return false;
  }, [call]);

  const loadCards = useCallback(async () => {
    const q = new URLSearchParams({ status, limit: "10", offset: String(offset) });
    if (category) q.set("category", category);
    const r = await call(`?${q.toString()}`);
    if (r.ok) setCards(r.body.cards ?? []);
  }, [call, status, category, offset]);

  useEffect(() => {
    if (secret) loadStats();
  }, [secret, loadStats]);

  useEffect(() => {
    if (authed) loadCards();
  }, [authed, loadCards]);

  // While a collection runs, keep the counts moving.
  useEffect(() => {
    if (!authed || !stats?.seed.running) return;
    const t = setInterval(() => {
      loadStats();
    }, 5000);
    return () => clearInterval(t);
  }, [authed, stats?.seed.running, loadStats]);

  function signIn() {
    try {
      sessionStorage.setItem(SECRET_KEY, entered);
    } catch {}
    setSecret(entered);
  }

  async function startSeed() {
    const r = await call("/seed", { method: "POST", body: JSON.stringify({ categories: seedCategory ? [seedCategory] : null, per_topic: perTopic }) });
    if (!r.ok) setError(typeof r.body.detail === "string" ? r.body.detail : "Couldn't start.");
    else setError("");
    loadStats();
  }

  function updateCard(id: string, patch: Partial<Card>) {
    setCards((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }

  async function save(card: Card) {
    const r = await call(`/${card.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: card.title,
        plain_summary: card.plain_summary,
        finding: card.finding,
        population: card.population,
        caution_notes: card.caution_notes,
        experiment_label: card.experiment_label || null,
      }),
    });
    if (r.ok) updateCard(card.id, { can_approve: r.body.can_approve, blocking_problems: r.body.blocking_problems, source: { ...card.source, checks: r.body.checks } });
    else setError(typeof r.body.detail === "string" ? r.body.detail : "Couldn't save.");
  }

  async function act(card: Card, action: "approve" | "reject" | "unapprove") {
    if (action === "approve") await save(card);
    const r = await call(`/${card.id}/${action}`, { method: "POST" });
    if (!r.ok) {
      const problems = Array.isArray(r.body.blocking_problems) ? r.body.blocking_problems.join(" ") : "";
      setError(`${typeof r.body.detail === "string" ? r.body.detail : "Couldn't do that."} ${problems}`);
      return;
    }
    setError("");
    setCards((prev) => prev.filter((c) => c.id !== card.id));
    loadStats();
  }

  if (!authed) {
    return (
      <div style={{ minHeight: "100vh", background: colors.bg, color: colors.text, padding: "80px 20px" }}>
        <div style={{ maxWidth: 380, margin: "0 auto" }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 14 }}>Evidence review</h1>
          <input type="password" placeholder="Password" value={entered} onChange={(e) => setEntered(e.target.value)} onKeyDown={(e) => e.key === "Enter" && signIn()} style={input} />
          <button onClick={signIn} style={{ ...button, marginTop: 12 }}>
            Sign in
          </button>
          {!!error && <p style={{ color: colors.bad, fontSize: 13, marginTop: 12 }}>{error}</p>}
        </div>
      </div>
    );
  }

  const seed = stats?.seed;
  return (
    <div style={{ minHeight: "100vh", background: colors.bg, color: colors.text, padding: "76px 20px 60px" }}>
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Evidence review</h1>
        <p style={{ color: colors.muted, fontSize: 13, marginBottom: 18 }}>
          Only cards you approve here ever reach the app. A card can be approved only when every automatic check passes.
        </p>

        {!!error && <p style={{ ...box, color: colors.bad, fontSize: 13 }}>{error}</p>}

        <div style={box}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 18, fontSize: 13 }}>
            {CATEGORIES.map(([key, label]) => {
              const c = stats?.by_category[key];
              return (
                <div key={key}>
                  <div style={{ fontWeight: 600 }}>{label}</div>
                  <div style={{ color: colors.muted }}>
                    <span style={{ color: colors.good }}>{c?.approved ?? 0}</span> approved · {c?.pending ?? 0} waiting · {c?.rejected ?? 0} rejected
                  </div>
                </div>
              );
            })}
          </div>
          <p style={{ fontSize: 13, marginTop: 12 }}>
            <strong>{stats?.totals.approved ?? 0}</strong> approved in total · {stats?.totals.pending ?? 0} waiting for review
          </p>
        </div>

        <div style={box}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Collect more studies</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <select value={seedCategory} onChange={(e) => setSeedCategory(e.target.value)} style={{ ...input, width: "auto" }}>
              <option value="">All categories</option>
              {CATEGORIES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <select value={perTopic} onChange={(e) => setPerTopic(Number(e.target.value))} style={{ ...input, width: "auto" }}>
              {[1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n} per topic
                </option>
              ))}
            </select>
            <button style={{ ...button, opacity: seed?.running ? 0.5 : 1 }} disabled={!!seed?.running} onClick={startSeed}>
              {seed?.running ? "Collecting…" : "Collect studies"}
            </button>
          </div>
          {seed && (seed.running || seed.topics_done > 0) && (
            <p style={{ color: colors.muted, fontSize: 12.5, marginTop: 10 }}>
              {seed.running ? `Working on: ${seed.current_topic}. ` : "Last run: "}
              {seed.topics_done} of {seed.topics_total} topics · {seed.added} added · {seed.skipped} skipped
              {seed.errors.length > 0 && ` · ${seed.errors.length} problems (latest: ${seed.errors[seed.errors.length - 1]})`}
            </p>
          )}
          <p style={{ color: colors.muted, fontSize: 12, marginTop: 6 }}>Each study takes a few seconds, so a full collection takes several minutes. New cards appear below as waiting for review.</p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {(["pending", "approved", "rejected"] as const).map((s) => (
            <button
              key={s}
              onClick={() => {
                setStatus(s);
                setOffset(0);
              }}
              style={{ ...button, background: status === s ? "rgba(34,211,238,0.12)" : "transparent" }}
            >
              {s === "pending" ? "Waiting for review" : s === "approved" ? "Approved" : "Rejected"}
            </button>
          ))}
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setOffset(0);
            }}
            style={{ ...input, width: "auto" }}
          >
            <option value="">All categories</option>
            {CATEGORIES.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {cards.length === 0 && <p style={{ color: colors.muted, fontSize: 14 }}>Nothing here.</p>}

        {cards.map((card) => {
          const c = card.source.checks;
          const badge = (ok: boolean | undefined, label: string) => (
            <span key={label} style={{ fontSize: 12, fontWeight: 600, color: ok ? colors.good : colors.bad, border: `1px solid ${ok ? colors.good : colors.bad}`, borderRadius: 999, padding: "2px 10px" }}>
              {ok ? "✓" : "✗"} {label}
            </span>
          );
          return (
            <div key={card.id} style={box}>
              <div style={{ color: colors.accent, fontSize: 11, fontWeight: 700, letterSpacing: 1 }}>
                {card.category.toUpperCase()} · {card.study_type.toUpperCase()} · {card.year ?? "year ?"} · {card.journal ?? "journal ?"}
                {card.sample_size ? ` · n=${card.sample_size.toLocaleString()}` : ""}
                {card.weight_related ? " · WEIGHT-RELATED" : ""}
              </div>
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>Title</label>
              <input style={input} value={card.title} onChange={(e) => updateCard(card.id, { title: e.target.value })} disabled={card.verified} />
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>Summary (2 to 4 sentences)</label>
              <textarea style={{ ...input, minHeight: 84 }} value={card.plain_summary} onChange={(e) => updateCard(card.id, { plain_summary: e.target.value })} disabled={card.verified} />
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>Finding (must say what research found; numbers must come from the abstract)</label>
              <textarea style={{ ...input, minHeight: 64 }} value={card.finding} onChange={(e) => updateCard(card.id, { finding: e.target.value })} disabled={card.verified} />
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>Who was studied</label>
              <input style={input} value={card.population ?? ""} onChange={(e) => updateCard(card.id, { population: e.target.value })} disabled={card.verified} />
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>Caution</label>
              <textarea style={{ ...input, minHeight: 56 }} value={card.caution_notes ?? ""} onChange={(e) => updateCard(card.id, { caution_notes: e.target.value })} disabled={card.verified} />
              <label style={{ display: "block", marginTop: 10, fontSize: 12, color: colors.muted }}>"Test it on yourself" behaviour (leave empty if it isn't a simple everyday habit; never a supplement)</label>
              <input style={input} value={card.experiment_label ?? ""} onChange={(e) => updateCard(card.id, { experiment_label: e.target.value })} disabled={card.verified} />
              <p style={{ color: colors.muted, fontSize: 12, marginTop: 8 }}>Matches goals on: {card.metric_tags.join(", ")}</p>
              {!!card.mentions_medication?.length && !card.verified && (
                <p style={{ color: "#f5a524", fontSize: 12.5, marginTop: 8 }}>
                  The abstract mentions medicine ({card.mentions_medication.join(", ")}). Cards about medicines usually shouldn't be approved.
                </p>
              )}

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                {badge(c.doi_ok, "DOI resolves")}
                {badge(c.title_match, "Title matches PubMed")}
                {badge(c.numbers_ok, "Numbers are in the abstract")}
                {badge(c.wording_ok, "Wording")}
              </div>
              {card.blocking_problems.length > 0 && !card.verified && (
                <ul style={{ color: colors.bad, fontSize: 12.5, marginTop: 8, paddingLeft: 18 }}>
                  {card.blocking_problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              )}

              {!c.numbers_ok && !!c.abstract_numbers?.length && !card.verified && (
                <p style={{ color: colors.muted, fontSize: 12.5, marginTop: 6 }}>Numbers the abstract does contain: {c.abstract_numbers.join(", ")}</p>
              )}

              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: "pointer", color: colors.accent, fontSize: 13 }}>Show the abstract this was drafted from</summary>
                <p style={{ color: colors.muted, fontSize: 13, lineHeight: 1.6, marginTop: 8 }}>{card.source.abstract}</p>
              </details>
              <p style={{ fontSize: 12.5, marginTop: 10 }}>
                <a href={card.url} target="_blank" rel="noreferrer" style={{ color: colors.accent }}>
                  Open on PubMed
                </a>
                {card.doi && (
                  <>
                    {" · "}
                    <a href={`https://doi.org/${card.doi}`} target="_blank" rel="noreferrer" style={{ color: colors.accent }}>
                      Open DOI
                    </a>
                  </>
                )}
              </p>

              <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
                {!card.verified && (
                  <>
                    <button style={button} onClick={() => save(card)}>
                      Save edits
                    </button>
                    <button style={{ ...button, color: colors.good, borderColor: colors.good }} onClick={() => act(card, "approve")}>
                      Approve
                    </button>
                    <button style={{ ...button, color: colors.bad, borderColor: colors.bad }} onClick={() => act(card, "reject")}>
                      Reject
                    </button>
                  </>
                )}
                {card.verified && (
                  <button style={{ ...button, color: colors.bad, borderColor: colors.bad }} onClick={() => act(card, "unapprove")}>
                    Take back out of use
                  </button>
                )}
              </div>
            </div>
          );
        })}

        <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
          <button style={{ ...button, opacity: offset === 0 ? 0.4 : 1 }} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 10))}>
            Previous
          </button>
          <button style={{ ...button, opacity: cards.length < 10 ? 0.4 : 1 }} disabled={cards.length < 10} onClick={() => setOffset(offset + 10)}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
