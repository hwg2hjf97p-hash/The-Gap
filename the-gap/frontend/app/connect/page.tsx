"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

// This route only exists because Whoop's registered OAuth redirect URI
// (and old links) point here. It immediately forwards to /results/live,
// which owns all the real connect + analysis logic.
function RedirectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    router.replace(`/results/live?${searchParams.toString()}`);
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a1710" }}>
      <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "#34d399", borderTopColor: "transparent" }} />
    </div>
  );
}

export default function ConnectRedirectPage() {
  return (
    <Suspense fallback={null}>
      <RedirectContent />
    </Suspense>
  );
}

export const dynamic = "force-dynamic";
