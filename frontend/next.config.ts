import type { NextConfig } from "next";
const api = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(api)) {
  throw new Error("Release 0.1 requires a loopback backend");
}
const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};
export default config;
