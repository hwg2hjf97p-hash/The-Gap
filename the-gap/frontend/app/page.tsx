"use client";

import { useRouter } from "next/navigation";
import { useState, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { analyseFile, AnalysisError } from "@/lib/api";
import type { DataSource } from "@/lib/types";
import ProgressBar from "@/components/ProgressBar";

const ACCEPTED_HEALTH: Record<string, string[]> = {
  "application/xml": [".xml"],
  "text/xml": [".xml"],
  "application/zip": [".zip"],
  "text/csv": [".csv"],
};

const ACCEPTED_CALENDAR: Record<string, string[]> = {
  "text/calendar": [".ics", ".ical"],
  "application/octet-stream": [".ics"],
};

// ── Custom SVG icons — brand-matched, no emoji ────────────────────────────────

function IconAppleHealth({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {/* Heart with ECG pulse line */}
      <path
        d="M12 21C12 21 3 15.5 3 9a4.5 4.5 0 0 1 9-0.75A4.5 4.5 0 0 1 21 9c0 6.5-9 12-9 12z"
        fill="#34d399"
        opacity="0.18"
        stroke="#34d399"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <polyline
        points="5,11 7.5,11 9,8.5 11,13.5 13,9.5 14.5,11 16,11 18,11"
        stroke="#34d399"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

function IconWhoop({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {/* Bold lightning bolt — Whoop's signature */}
      <path
        d="M13 3L5 13.5h6L9 21l10-10.5h-6L13 3z"
        fill="#c9a84c"
        stroke="#c9a84c"
        strokeWidth="0.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconOura({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {/* Clean geometric ring — thick circle with inner highlight */}
      <circle cx="12" cy="12" r="7.5" stroke="#c9a84c" strokeWidth="2.8" fill="none" />
      <circle cx="12" cy="12" r="4" stroke="#c9a84c" strokeWidth="1" fill="none" opacity="0.35" />
      <circle cx="9.5" cy="8.5" r="1.2" fill="#c9a84c" opacity="0.7" />
    </svg>
  );
}

function IconCalendar({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="5" width="18" height="16" rx="2" stroke="#a2bcaf" strokeWidth="1.6" fill="none" />
      <path d="M3 10h18" stroke="#a2bcaf" strokeWidth="1.4" />
      <path d="M8 3v4M16 3v4" stroke="#a2bcaf" strokeWidth="1.6" strokeLinecap="round" />
      <rect x="7" y="13" width="3" height="3" rx="0.5" fill="#34d399" opacity="0.7" />
      <rect x="14" y="13" width="3" height="3" rx="0.5" fill="#a2bcaf" opacity="0.4" />
    </svg>
  );
}

function IconFile({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
        stroke="#c9a84c" strokeWidth="1.6" fill="none" strokeLinejoin="round"
      />
      <path d="M14 2v6h6" stroke="#c9a84c" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13h8M8 17h5" stroke="#c9a84c" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

// ── Source definitions ────────────────────────────────────────────────────────
const SOURCES = [
  {
    id: "apple_health" as DataSource,
    label: "Apple Health",
    Icon: IconAppleHealth,
    hint: "Health app → profile photo → Export All Health Data",
    accept: ".xml or .zip",
  },
  {
    id: "whoop" as DataSource,
    label: "Whoop",
    Icon: IconWhoop,
    hint: "Whoop app → More → App Settings → Export Data",
    accept: ".csv export",
  },
  {
    id: "oura" as DataSource,
    label: "Oura",
    Icon: IconOura,
    hint: "Oura app → Profile → Data Export → Export to CSV",
    accept: ".csv or .json export",
  },
];

export default function HomePage() {
  const router = useRouter();
  const [dataSource, setDataSource] = useState<DataSource>("apple_health");
  const [file, setFile] = useState<File | null>(null);
  const [calendarFile, setCalendarFile] = useState<File | null>(null);
  const [showCalendar, setShowCalendar] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState("");
  const [status, setStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const progressInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentSource = SOURCES.find((s) => s.id === dataSource)!;

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED_HEALTH,
    maxFiles: 1,
    onDrop: (accepted) => {
      if (accepted.length > 0) {
        setFile(accepted[0]);
        setErrorMsg("");
        setStatus("idle");
      }
    },
  });

  const {
    getRootProps: getCalRootProps,
    getInputProps: getCalInputProps,
    isDragActive: isCalDragActive,
  } = useDropzone({
    accept: ACCEPTED_CALENDAR,
    maxFiles: 1,
    onDrop: (accepted) => {
      if (accepted.length > 0) setCalendarFile(accepted[0]);
    },
  });

  function startProgressSimulation() {
    setProgress(0);
    let current = 0;
    progressInterval.current = setInterval(() => {
      current += Math.random() * 1.2;
      if (current >= 90) {
        current = 90;
        clearInterval(progressInterval.current!);
      }
      setProgress(Math.round(current));
    }, 600);
  }

  function finishProgress() {
    if (progressInterval.current) clearInterval(progressInterval.current);
    setProgress(100);
  }

  async function handleAnalyse() {
    if (!file) return;
    setStatus("uploading");
    setErrorMsg("");
    setStatusLabel("Uploading your data…");
    startProgressSimulation();

    try {
      const result = await analyseFile(file, dataSource, calendarFile || undefined, (pct) => {
        if (pct >= 95) setStatusLabel("Running causal analysis… this takes ~20 seconds");
      });

      finishProgress();
      sessionStorage.setItem("gap_results", JSON.stringify(result));
      router.push(`/results/${result.session_id}`);
    } catch (err) {
      if (progressInterval.current) clearInterval(progressInterval.current);
      setStatus("error");
      if (err instanceof AnalysisError) {
        if (err.code === "NETWORK_ERROR") {
          setErrorMsg("The analysis server took too long to respond. Please try again — it usually works on the second attempt.");
        } else if (err.code === "INSUFFICIENT_DATA") {
          setErrorMsg(err.message);
        } else if (err.code === "NO_INSIGHTS") {
          setErrorMsg("No significant patterns found yet. Try again after 60+ days of data.");
        } else {
          setErrorMsg(err.message || "Something went wrong. Please try again.");
        }
      } else {
        setErrorMsg("Something went wrong. Please try again.");
      }
    }
  }

  const isUploading = status === "uploading";

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-16">

      {/* Hero */}
      <div className="text-center max-w-2xl mb-10">
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono mb-6"
          style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}
        >
          ✦ Verified cause &amp; effect · not just correlation
        </div>
        <h1
          className="text-5xl font-bold tracking-tight mb-4 leading-tight"
          style={{ color: "#eef3f0" }}
        >
          What actually{" "}
          <span style={{ color: "#34d399" }}>moves the needle</span>
          <br />for your health?
        </h1>
        <p className="text-lg leading-relaxed" style={{ color: "#a2bcaf" }}>
          Upload your health data. The Gap runs causal inference across 26 hypotheses
          and tells you what genuinely causes what — not just what correlates.
        </p>
      </div>

      {/* Upload card */}
      <div
        className="w-full max-w-lg rounded-2xl p-8"
        style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
      >

        {/* Source toggle — 3 options */}
        <div
          className="flex rounded-xl overflow-hidden mb-6"
          style={{ background: "#0a1710" }}
        >
          {SOURCES.map((src) => (
            <button
              key={src.id}
              onClick={() => { setDataSource(src.id); setFile(null); setErrorMsg(""); }}
              className="flex-1 py-2.5 text-sm font-medium transition-all flex items-center justify-center gap-1.5"
              style={{
                background: dataSource === src.id ? "#1a3d2b" : "transparent",
                color: dataSource === src.id ? "#eef3f0" : "#a2bcaf",
                borderRadius: "0.75rem",
              }}
            >
              <src.Icon size={16} />
              {src.label}
            </button>
          ))}
        </div>

        {/* Health data dropzone */}
        <div
          {...getRootProps()}
          className="rounded-xl p-8 text-center cursor-pointer transition-all duration-200"
          style={{
            border: `2px dashed ${isDragActive ? "#34d399" : file ? "#c9a84c" : "#1a3d2b"}`,
            background: isDragActive ? "rgba(52,211,153,0.04)" : "#0a1710",
          }}
        >
          <input {...getInputProps()} />
          {file ? (
            <div className="flex flex-col items-center">
              <div className="mb-2"><IconFile size={28} /></div>
              <p className="font-medium" style={{ color: "#eef3f0" }}>{file.name}</p>
              <p className="text-sm mt-1" style={{ color: "#a2bcaf" }}>
                {(file.size / (1024 * 1024)).toFixed(1)} MB · Click to change
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <div className="mb-3"><currentSource.Icon size={36} /></div>
              <p className="font-medium mb-1" style={{ color: "#eef3f0" }}>
                {isDragActive ? "Drop it here" : `Drop your ${currentSource.label} export`}
              </p>
              <p className="text-sm" style={{ color: "#a2bcaf" }}>
                {currentSource.accept} · up to 500 MB
              </p>
            </div>
          )}
        </div>

        {/* How to export hint */}
        <p className="text-xs mt-2 text-center" style={{ color: "#a2bcaf" }}>
          {currentSource.hint}
        </p>

        {/* Google Calendar add-on */}
        <div className="mt-5">
          <button
            onClick={() => setShowCalendar(!showCalendar)}
            className="w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm transition-all"
            style={{
              background: showCalendar ? "#1a3d2b" : "#0a1710",
              color: showCalendar ? "#eef3f0" : "#a2bcaf",
              border: `1px solid ${showCalendar ? "#34d399" : "#1a3d2b"}`,
            }}
          >
            <span className="flex items-center gap-2">
              <IconCalendar size={16} />
              <span>Add Google Calendar</span>
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: "#c9a84c22", color: "#c9a84c" }}
              >
                Unlocks 5 more insights
              </span>
            </span>
            <span style={{ color: "#a2bcaf" }}>{showCalendar ? "▲" : "▼"}</span>
          </button>

          {showCalendar && (
            <div className="mt-3">
              <div
                {...getCalRootProps()}
                className="rounded-xl p-5 text-center cursor-pointer transition-all"
                style={{
                  border: `2px dashed ${isCalDragActive ? "#34d399" : calendarFile ? "#c9a84c" : "#1a3d2b"}`,
                  background: "#0a1710",
                }}
              >
                <input {...getCalInputProps()} />
                {calendarFile ? (
                  <div>
                    <p className="font-medium text-sm" style={{ color: "#eef3f0" }}>
                      {calendarFile.name}
                    </p>
                    <p className="text-xs mt-1" style={{ color: "#34d399" }}>
                      Calendar data will be merged · Click to change
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-medium mb-1" style={{ color: "#eef3f0" }}>
                      Drop your calendar export (.ics)
                    </p>
                    <p className="text-xs" style={{ color: "#a2bcaf" }}>
                      Google Calendar → Settings → Import &amp; Export → Export
                    </p>
                  </div>
                )}
              </div>
              <p className="text-xs mt-2 text-center" style={{ color: "#a2bcaf" }}>
                Analyses meeting load, late meetings, and busy-day effects on your health
              </p>
            </div>
          )}
        </div>

        {/* Progress */}
        {isUploading && (
          <div className="mt-5">
            <ProgressBar value={progress} />
            <p className="text-xs text-center mt-2" style={{ color: "#a2bcaf" }}>
              {statusLabel || "Analysing your data…"}
            </p>
          </div>
        )}

        {/* Error */}
        {status === "error" && errorMsg && (
          <div
            className="mt-4 p-4 rounded-lg text-sm"
            style={{
              background: "rgba(201,168,76,0.08)",
              color: "#c9a84c",
              border: "1px solid rgba(201,168,76,0.2)",
            }}
          >
            {errorMsg}
          </div>
        )}

        {/* CTA */}
        <button
          onClick={handleAnalyse}
          disabled={!file || isUploading}
          className="w-full mt-6 py-3.5 rounded-xl font-semibold text-sm transition-all duration-200"
          style={{
            background: file && !isUploading ? "#34d399" : "#1a3d2b",
            color: file && !isUploading ? "#0a1710" : "#a2bcaf",
            cursor: file && !isUploading ? "pointer" : "not-allowed",
          }}
        >
          {isUploading
            ? "Analysing your data…"
            : calendarFile
            ? `Find my causal patterns (health + calendar) →`
            : "Find my causal patterns →"}
        </button>
      </div>

      {/* Passive mode CTA */}
      <div className="w-full max-w-lg mt-4">
        <a
          href="/connect"
          className="flex items-center justify-between px-5 py-4 rounded-xl transition-all"
          style={{
            background: "#132c1f",
            border: "1px solid #1a3d2b",
            textDecoration: "none",
          }}
        >
          <div className="flex items-center gap-3">
            <IconWhoop size={20} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#eef3f0" }}>
                Have a Whoop, Oura, or Strava?
              </p>
              <p className="text-xs" style={{ color: "#a2bcaf" }}>
                Connect once — insights update automatically every day
              </p>
            </div>
          </div>
          <span style={{ color: "#34d399", fontSize: "1.1rem" }}>→</span>
        </a>
      </div>

      {/* Trust signals */}
      <div
        className="mt-6 flex flex-wrap justify-center gap-6 text-xs"
        style={{ color: "#a2bcaf" }}
      >
        <span>🔒 Your data never leaves our servers</span>
        <span>⚡ Results in under 60 seconds</span>
        <span>🧬 26 causal hypotheses · Microsoft EconML</span>
      </div>
    </div>
  );
}
