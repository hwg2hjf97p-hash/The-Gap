import type { Metadata, Viewport } from "next";
import "./globals.css";
import ChromeWrapper from "../components/ChromeWrapper";
import SiteBackdrop from "../components/SiteBackdrop";

const TITLE = "The Gap app by CausalMe";
const DESCRIPTION =
  "The Gap is an iPhone app that shows what seems to affect your sleep, HRV and recovery, using your own data from Apple Health, Apple Watch, Whoop, Oura and more.";

export const metadata: Metadata = {
  title: { default: TITLE, template: "%s | The Gap app by CausalMe" },
  description: DESCRIPTION,
  metadataBase: new URL("https://www.causalme.com"),
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://www.causalme.com",
    siteName: "The Gap",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
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
    <html lang="en-AU">
      <body className="min-h-screen" style={{ backgroundColor: "#0b1015" }}>
        <SiteBackdrop />
        <div className="relative z-10">
          <ChromeWrapper>{children}</ChromeWrapper>
        </div>
      </body>
    </html>
  );
}
