import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  typedRoutes: false,
  // ENH-003 security review: the reset / set-password link carries a live token in its query
  // string -- never send it as a Referer and ask for it not to be cached.
  async headers() {
    return [
      {
        source: "/:division(it|overseas)/reset-password",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
};

export default nextConfig;
