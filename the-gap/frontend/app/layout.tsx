import type { Metadata, Viewport } from "next";
import "./globals.css";
import ChromeWrapper from "../components/ChromeWrapper";

const TITLE = "The Gap: don't just know what. Know why.";
const DESCRIPTION =
  "The Gap finds the habits that actually move your sleep, recovery and energy, using your own data from Apple Health, Whoop, Oura and more. In private testing on iPhone.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  metadataBase: new URL("https://causalme.com"),
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://causalme.com",
    siteName: "The Gap",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "The Gap" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og-image.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#0b1015",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen" style={{ backgroundColor: "#0b1015" }}>
        <ChromeWrapper>{children}</ChromeWrapper>
      </body>
    </html>
  );
}
