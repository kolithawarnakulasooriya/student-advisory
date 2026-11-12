import { defineConfig } from "@playwright/test";
const apiPort = process.env.ADVISORY_E2E_API_PORT ?? "8000";
const webPort = process.env.ADVISORY_E2E_WEB_PORT ?? "3000";
const webOrigin = `http://localhost:${webPort}`;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: webOrigin,
    trace: "off",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `../backend/.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      cwd: "../backend",
      url: `http://127.0.0.1:${apiPort}/api/v1/health/ready`,
      env: { WEB_ORIGIN: webOrigin },
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      env: {
        API_INTERNAL_URL: `http://127.0.0.1:${apiPort}`,
        ADVISORY_NEXT_DIST_DIR:
          webPort === "3000" ? ".next" : `.next-e2e-${webPort}`,
      },
      url: webOrigin,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
