import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // In production the frontend calls the backend directly via NEXT_PUBLIC_STREAM_URL.
    // Rewrites are only needed for local dev where both run on localhost.
    if (process.env.NODE_ENV === "production") return [];
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
