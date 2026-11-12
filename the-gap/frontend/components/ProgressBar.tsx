"use client";

interface Props {
  value: number; // 0–100
}

export default function ProgressBar({ value }: Props) {
  return (
    <div className="w-full rounded-full h-1.5 overflow-hidden"
         style={{ background: "#2f2a23" }}>
      <div
        className="h-full rounded-full transition-all duration-300 ease-out"
        style={{
          width: `${Math.min(100, Math.max(0, value))}%`,
          background: "linear-gradient(to right, #e0a458, #e0a458)",
        }}
      />
    </div>
  );
}
