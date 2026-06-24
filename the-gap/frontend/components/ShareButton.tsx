"use client";

import { useState } from "react";

interface Props {
  shareUrl: string;
}

export default function ShareButton({ shareUrl }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback: select input
      const input = document.createElement("input");
      input.value = shareUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      document.body.removeChild(input);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm transition-all duration-200"
      style={{
        background: copied ? "#1a3d2b" : "#132c1f",
        color: copied ? "#34d399" : "#eef3f0",
        border: `1px solid ${copied ? "#34d399" : "#1a3d2b"}`,
      }}
    >
      {copied ? (
        <>
          <span>✓</span>
          Link copied
        </>
      ) : (
        <>
          <span>🔗</span>
          Share your results
        </>
      )}
    </button>
  );
}
