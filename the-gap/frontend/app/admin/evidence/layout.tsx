import type { Metadata } from "next";
import type { ReactNode } from "react";

// A private tool: kept out of search engines and not linked from anywhere on the site.
export const metadata: Metadata = {
  title: "Evidence review",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
