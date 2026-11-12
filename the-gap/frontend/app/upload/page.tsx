"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, FileCheck2 } from "lucide-react";
import { analyseFile, AnalysisError } from "../../lib/api";
import type { DataSource, UploadState } from "../../lib/types";

const SOURCES: { id: DataSource; label: string; hint: string }[] = [
  { id: "apple_health", label: "Apple Health", hint: ".zip or .xml export from the Health app" },
  { id: "whoop", label: "Whoop", hint: ".csv export from the Whoop app" },
  { id: "oura", label: "Oura", hint: ".csv or .json export from the Oura app" },
];

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const calendarInputRef = useRef<HTMLInputElement>(null);

  const [dataSource, setDataSource] = useState<DataSource>("apple_health");
  const [file, setFile] = useState<File | null>(null);
  const [calendarFile, setCalendarFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);

  function handleFileSelect(f: File) {
    setFile(f);
    setState("selected");
    setError("");
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFileSelect(f);
  }

  async function handleAnalyse() {
    if (!file) return;
    setState("uploading");
    setProgress(0);
    setError("");
    try {
      const result = await analyseFile(
        file,
        dataSource,
        calendarFile ?? undefined,
        (pct) => {
          setProgress(pct);
          if (pct >= 100) setState("processing");
        }
      );
      setState("done");
      sessionStorage.setItem("gap_results", JSON.stringify(result));
      router.push(`/results/${result.session_id}`);
    } catch (err) {
      setState("error");
      if (err instanceof AnalysisError) {
        setError(err.message);
      } else {
        setError("Something went wrong. Please try again.");
      }
    }
  }

  const isBusy = state === "uploading" || state === "processing";

  return (
    <div className="min-h-screen px-4 py-16" style={{ background: "#16130f" }}>
      <div className="max-w-lg mx-auto">
        <p className="text-xs font-mono tracking-widest mb-3 text-center" style={{ color: "#e0a458" }}>
          NO ACCOUNT NEEDED
        </p>
        <h1 className="text-3xl font-bold text-center mb-3" style={{ color: "#f1ebe2" }}>
          Analyse a data export
        </h1>
        <p className="text-sm text-center mb-8" style={{ color: "#a0968a" }}>
          One-off analysis of a file you already have — no connected account,
          nothing stored beyond this session unless you save the link.
        </p>

        {/* Data source selector */}
        <div className="flex gap-2 mb-6">
          {SOURCES.map((s) => (
            <button
              key={s.id}
              onClick={() => setDataSource(s.id)}
              className="flex-1 px-3 py-2 rounded-xl text-sm font-medium"
              style={{
                background: dataSource === s.id ? "#e0a458" : "#211d18",
                color: dataSource === s.id ? "#16130f" : "#a0968a",
                border: `1px solid ${dataSource === s.id ? "#e0a458" : "#2f2a23"}`,
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-center mb-6" style={{ color: "#857c71" }}>
          {SOURCES.find((s) => s.id === dataSource)?.hint}
        </p>

        {/* Drop zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className="rounded-2xl p-8 text-center cursor-pointer mb-4"
          style={{
            background: "#211d18",
            border: `2px dashed ${dragActive ? "#e0a458" : "#2f2a23"}`,
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".zip,.xml,.csv,.json"
            onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
          />
          {file ? (
            <>
              <FileCheck2 size={28} color="#e0a458" className="mx-auto mb-2" />
              <p className="text-sm font-medium" style={{ color: "#f1ebe2" }}>
                {file.name}
              </p>
              <p className="text-xs mt-1" style={{ color: "#a0968a" }}>
                Tap to choose a different file
              </p>
            </>
          ) : (
            <>
              <UploadCloud size={28} color="#a0968a" className="mx-auto mb-2" />
              <p className="text-sm font-medium" style={{ color: "#f1ebe2" }}>
                Drop your file here, or tap to browse
              </p>
            </>
          )}
        </div>

        {/* Optional calendar file */}
        <button
          onClick={() => calendarInputRef.current?.click()}
          className="w-full text-sm text-center mb-6"
          style={{ color: "#e0a458" }}
        >
          {calendarFile ? `Calendar: ${calendarFile.name} (tap to change)` : "+ Add a Google Calendar export (optional)"}
        </button>
        <input
          ref={calendarInputRef}
          type="file"
          className="hidden"
          accept=".ics"
          onChange={(e) => e.target.files?.[0] && setCalendarFile(e.target.files[0])}
        />

        {error && (
          <p className="text-sm text-center mb-4" style={{ color: "#f87171" }}>
            {error}
          </p>
        )}

        <button
          onClick={handleAnalyse}
          disabled={!file || isBusy}
          className="w-full py-3 rounded-xl font-semibold text-sm disabled:opacity-40"
          style={{ background: "#e0a458", color: "#16130f" }}
        >
          {state === "uploading"
            ? `Uploading… ${progress}%`
            : state === "processing"
            ? "Running your analysis…"
            : "Analyse my data →"}
        </button>

        <p className="text-xs text-center mt-6" style={{ color: "#857c71" }}>
          Prefer live, automatic tracking?{" "}
          <a href="/settings" style={{ color: "#e0a458" }}>
            Connect a device instead →
          </a>
        </p>
      </div>
    </div>
  );
}
