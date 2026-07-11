import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output (a self-contained server bundle) is only needed for the
  // Docker image. Enable it via BUILD_STANDALONE=1 in the Dockerfile so local
  // `next build && next start` stays warning-free.
  output: process.env.BUILD_STANDALONE ? "standalone" : undefined,
  reactStrictMode: true,
};

export default nextConfig;
