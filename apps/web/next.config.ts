import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // API calls are proxied at runtime by src/app/api/[...path]/route.ts
  // (build-time rewrites cannot see INTERNAL_API_URL injected by docker-compose).
};

export default nextConfig;
