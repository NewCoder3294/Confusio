import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin Turbopack's workspace root to this dir; the parent has a stray
  // package-lock.json from the SynthIDBye TS runner which Turbopack
  // otherwise tries to claim as the root. cwd() works because the dev
  // server is always launched from this directory.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
