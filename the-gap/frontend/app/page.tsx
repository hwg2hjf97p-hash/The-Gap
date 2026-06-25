"use client";

import { useRouter } from "next/navigation";
import { useState, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { analyseFile, AnalysisError } from "@/lib/api";
import type { DataSource } from "@/lib/types";
import ProgressBar from "@/components/ProgressBar";

const ACCEPTED: Record<string, string[]> = {
  "application/xml": [".xml"],
  "text/xml": [".xml"],
  "application/zip": [".zip"],
  "text/csv": [".csv"],
};

const STEPS = [
  { icon: "⬆️", label: "Upload your export", desc: "Apple Health XML/ZIP or Whoop CSV" },
  { icon: "🔬", label: "Causal engine runs", desc: "Double ML isolates cause from correlation" },
  { icon: "✦",  label: "Get verified insights", desc: "Real cause-and-effect patterns, not guesses" },
];

export default function HomePage() {
  const router = useRouter();
  const [dataSource, setDataSource] = useState<DataSource>("apple_health");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState("");
  const [status, setStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const progressInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED,
    maxFiles: 1,
    onDrop: (accepted) => {
      if (accepted.length > 0) {
        setFile(accepted[0]);
        setErrorMsg("");
        setStatus("idle");
      }
    },
  });

  function startProgressSimulation() {
    // Smoothly animate from 0 → 90% over ~45s while waiting for analysis
    setProgress(0);
    let current = 0;
    progressInterval.current = setInterval(() => {
      current += Math.random() * 1.5;
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
      const result = await analyseFile(file, dataSource, (pct) => {
        if (pct < 95) setProgress(Math.round(pct * 0.4)); // upload = first 40%
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
          setErrorMsg("No significant patterns found yet. Try again after 60+ days of Whoop/Apple Health data.");
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
      <div className="text-center max-w-2xl mb-12 animate-fade-in">
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
          Upload your Apple Health or Whoop export. The Gap runs causal inference
          on your data and tells you what genuinely causes what — not just what
          tends to happen at the same time.
        </p>
      </div>

      {/* Upload card */}
      <div
        className="w-full max-w-lg rounded-2xl p-8 animate-slide-up"
        style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}
      >
        {/* Source toggle */}
        <div
          className="flex rounded-xl overflow-hidden mb-6"
          style={{ background: "#0a1710" }}
        >
          {(["apple_health", "whoop"] as DataSource[]).map((src) => (
            <button
              key={src}
              onClick={() => { setDataSource(src); setFile(null); setErrorMsg(""); }}
              className="flex-1 py-2.5 text-sm font-medium transition-all"
              style={{
                background: dataSource === src ? "#1a3d2b" : "transparent",
                color: dataSource === src ? "#eef3f0" : "#a2bcaf",
                borderRadius: "0.75rem",
              }}
            >
              {src === "apple_health" ? "🍎 Apple Health" : "⚡ Whoop"}
            </button>
          ))}
        </div>

        {/* Dropzone */}
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
              <div className="text-3xl mb-3">⬆️</div>
              <p className="font-medium mb-1" style={{ color: "#eef3f0" }}>
                {isDragActive ? "Drop it here" : "Drop your export here"}
              </p>
              <p className="text-sm" style={{ color: "#a2bcaf" }}>
                {dataSource === "apple_health"
                  ? "export.xml or export.zip — up to 500 MB"
                  : "CSV export from your Whoop app"}
              </p>
            </div>
          )}
        </div>

        {/* How to export hint */}
        <p className="text-xs mt-3 text-center" style={{ color: "#a2bcaf" }}>
          {dataSource === "apple_health"
            ? "Health app → your profile photo → Export All Health Data"
            : "Whoop app → More → App Settings → Export Data"}
        </p>

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
          {isUploading ? "Analysing your data…" : "Find my causal patterns →"}
        </button>
      </div>

      {/* How it works */}
      <div className="w-full max-w-lg mt-8 animate-fade-in">
        <div className="flex justify-between gap-4">
          {STEPS.map((step, i) => (
            <div key={i} className="flex-1 text-center">
              <div className="text-xl mb-1">{step.icon}</div>
              <p className="text-xs font-medium mb-0.5" style={{ color: "#eef3f0" }}>
                {step.label}
              </p>
              <p className="text-xs" style={{ color: "#a2bcaf" }}>
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Trust signals */}
      <div
        className="mt-8 flex flex-wrap justify-center gap-6 text-xs animate-fade-in"
        style={{ color: "#a2bcaf" }}
      >
        <span>🔒 Your data is never stored</span>
        <span>⚡ Results in under 60 seconds</span>
        <span>🧬 Powered by Microsoft EconML</span>
      </div>
    </div>
  );
}
