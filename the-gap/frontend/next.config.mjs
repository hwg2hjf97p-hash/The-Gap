/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
  // causalme.com is now an information page only. The old web tools (upload,
  // connect, journal, insights, assistant, settings, shared results) are no
  // longer offered, so anyone arriving at an old link lands on the home page.
  async redirects() {
    const retired = ["/upload", "/connect", "/journal", "/insights", "/assistant", "/settings"];
    return [
      ...retired.map((source) => ({ source, destination: "/", permanent: false })),
      { source: "/results/:path*", destination: "/", permanent: false },
    ];
  },
};

export default nextConfig;
