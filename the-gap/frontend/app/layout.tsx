import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Gap — Your Personal Causal Intelligence Layer",
  description:
    "Upload your Apple Health or Whoop data and discover verified cause-and-effect patterns in your own health. Not correlations — actual causation.",
  metadataBase: new URL("https://causalme.com"),
  openGraph: {
    title: "The Gap",
    description: "Discover verified cause-and-effect patterns in your health data.",
    url: "https://causalme.com",
    siteName: "The Gap",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "The Gap",
    description: "Verified cause-and-effect in your health data.",
  },
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen" style={{ backgroundColor: "#0a1710" }}>
        {/* Top nav bar */}
        <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
             style={{ background: "linear-gradient(to bottom, rgba(10,23,16,0.95), transparent)" }}>
          <a href="/" className="flex items-center gap-2">
            <span className="text-xl font-semibold tracking-tight" style={{ color: "#eef3f0" }}>
              The Gap
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full font-mono"
                  style={{ background: "#132c1f", color: "#34d399", border: "1px solid #1a3d2b" }}>
              beta
            </span>
          </a>
          <a
            href="https://www.causalme.com"
            className="text-sm font-medium transition-colors"
            style={{ color: "#a2bcaf" }}
          >
            causalme.com
          </a>
        </nav>

        {/* Page content */}
        <main className="pt-16">{children}</main>

        {/* Footer */}
        <footer className="mt-24 pb-12 text-center"
                style={{ color: "#a2bcaf", fontSize: "0.75rem" }}>
          <p>
            © 2026 The Gap · Samuel Roberts ·{" "}
            <a href="mailto:hello@causalme.com"
               className="hover:text-text transition-colors"
               style={{ color: "#c9a84c" }}>
              hello@causalme.com
            </a>
          </p>
          <p className="mt-1 opacity-60">
            Causal inference powered by EconML (Microsoft Research)
          </p>
        </footer>
      </body>
    </html>
  );
}
