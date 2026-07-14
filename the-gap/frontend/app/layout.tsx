import type { Metadata } from "next";
import "./globals.css";
import ChromeWrapper from "../components/ChromeWrapper";

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
        <ChromeWrapper>{children}</ChromeWrapper>
      </body>
    </html>
  );
}
