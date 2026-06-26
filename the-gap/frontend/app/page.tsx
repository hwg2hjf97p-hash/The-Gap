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

const SOURCES = [
  {
    id: "apple_health" as DataSource,
    label: "Apple Health",
    icon: "🍎",
    hint: "Health app → profile photo → Export All Health Data",
    accept: ".xml or .zip",
  },
  {
    id: "whoop" as DataSource,
    label: "Whoop",
    icon: "⚡",
    hint: "Whoop app → More → App Settings → Export Data",
    accept: ".csv export",
  },
  {
    id: "oura" as DataSource,
    label: "Oura",
    icon: "💍",
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
          Upload your health data. The Gap runs causal inference across 22 hypotheses
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
              className="flex-1 py-2.5 text-sm font-medium transition-all"
              style={{
                background: dataSource === src.id ? "#1a3d2b" : "transparent",
                color: dataSource === src.id ? "#eef3f0" : "#a2bcaf",
                borderRadius: "0.75rem",
              }}
            >
              {src.icon} {src.label}
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
            <div>
              <div className="text-2xl mb-2">📄</div>
              <p className="font-medium" style={{ color: "#eef3f0" }}>{file.name}</p>
              <p className="text-sm mt-1" style={{ color: "#a2bcaf" }}>
                {(file.size / (1024 * 1024)).toFixed(1)} MB · Click to change
              </p>
            </div>
          ) : (
            <div>
              <div className="text-3xl mb-3">{currentSource.icon}</div>
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
              📅 <span>Add Google Calendar</span>
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: "#c9a84c22", color: "#c9a84c" }}
              >
                New — unlocks 5 more insights
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
                      📅 {calendarFile.name}
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

      {/* Trust signals */}
      <div
        className="mt-8 flex flex-wrap justify-center gap-6 text-xs"
        style={{ color: "#a2bcaf" }}
      >
        <span>🔒 Your data never leaves our servers</span>
        <span>⚡ Results in under 60 seconds</span>
        <span>🧬 22 causal hypotheses · Microsoft EconML</span>
      </div>
    </div>
  );
}
