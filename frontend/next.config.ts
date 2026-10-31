import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Experimental request/component caching is left off: this app serves
  // per-organization, per-station authenticated data, and an aggressive
  // cache default is the wrong tradeoff until each page's caching rules
  // are deliberately reviewed.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
