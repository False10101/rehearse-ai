import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async redirects() {
    return [{ source: "/login", destination: "/", permanent: false }];
  },
};

export default nextConfig;
