"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
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

export default function HomePage() {
  const router = useRouter();
  const [dataSource, setDataSource] = useState<DataSource>("apple_health");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED,
    maxFiles: 1,
    onDrop: (accepted) => {
      if (accepted.length > 0) {
        setFile(accepted[0]);
        setErrorMsg("");
      }
    },
  });

  async function handleAnalyse() {
    if (!file) return;
    setStatus("uploading");
    setProgress(0);
    setErrorMsg("");

    try {
      const result = await analyseFile(file, dataSource, (pct) => {
        // First 80% is upload, last 20% is processing
        setProgress(Math.round(pct * 0.8));
      });

      // Save results to sessionStorage for the results page
      sessionStorage.setItem("gap_results", JSON.stringify(result));
      setProgress(100);
      router.push(`/results/${result.session_id}`);
    } catch (err) {
      setStatus("error");
      if (err instanceof AnalysisError) {
        setErrorMsg(err.message);
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
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono mb-6"
             style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}>
          ✦ Verified cause & effect · not just correlation
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-4 leading-tight"
            style={{ color: "#eef3f0" }}>
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
      <div className="w-full max-w-lg rounded-2xl p-8 animate-slide-up"
           style={{ background: "#132c1f", border: "1px solid #1a3d2b" }}>

        {/* Source toggle */}
        <div className="flex rounded-xl overflow-hidden mb-6"
             style={{ background: "#0a1710" }}>
          {(["apple_health", "whoop"] as DataSource[]).map((src) => (
            <button
              key={src}
              onClick={() => setDataSource(src)}
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
                  ? "export.xml or export.zip from Apple Health"
                  : "CSV export from Whoop app"}
              </p>
            </div>
          )}
        </div>

        {/* How to export hint */}
        <p className="text-xs mt-3 text-center" style={{ color: "#a2bcaf" }}>
          {dataSource === "apple_health"
            ? "Apple Health → Profile icon → Export All Health Data"
            : "Whoop app → More → App Settings → Export Data"}
        </p>

        {/* Progress bar */}
        {isUploading && (
          <div className="mt-5">
            <ProgressBar value={progress} />
            <p className="text-xs text-center mt-2" style={{ color: "#a2bcaf" }}>
              {progress < 80 ? "Uploading…" : "Running causal analysis…"}
            </p>
          </div>
        )}

        {/* Error */}
        {status === "error" && errorMsg && (
          <div className="mt-4 p-3 rounded-lg text-sm"
               style={{ background: "rgba(201,168,76,0.1)", color: "#c9a84c", border: "1px solid rgba(201,168,76,0.2)" }}>
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
          {isUploading ? "Analysing…" : "Find my causal patterns →"}
        </button>
      </div>

      {/* Trust signals */}
      <div className="mt-10 flex flex-wrap justify-center gap-6 text-xs animate-fade-in"
           style={{ color: "#a2bcaf" }}>
        <span>🔒 Data never stored beyond your session</span>
        <span>⚡ Results in under 60 seconds</span>
        <span>🧬 Powered by Microsoft EconML</span>
      </div>
    </div>
  );
}
