import type { Metadata, Viewport } from "next";
import "./globals.css";
import ChromeWrapper from "../components/ChromeWrapper";

const TITLE = "The Gap";
const DESCRIPTION = "The Gap by CausalMe.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  metadataBase: new URL("https://causalme.com"),
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://causalme.com",
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
    <html lang="en">
      <body className="min-h-screen" style={{ backgroundColor: "#0b1015" }}>
        <ChromeWrapper>{children}</ChromeWrapper>
      </body>
    </html>
  );
}
