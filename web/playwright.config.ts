import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3024);
const BASE_URL = `http://localhost:${PORT}`;

/**
 * E2E config. Boots a production server (`next start`) pointed at the live local
 * stack (Prometheus :9090 / Loki :3100) and drives it with the system Google
 * Chrome (channel "chrome") — Playwright's bundled Chromium isn't available for
 * this OS build.
 */
export default defineConfig({
  testDir: "./e2e",
  // auth.spec.ts → playwright.auth.config.ts; visual.spec.ts → playwright.visual.config.ts.
  testIgnore: /(auth|visual)\.spec\.ts/,
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  webServer: {
    command: `npx next start -p ${PORT}`,
    url: BASE_URL,
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
    env: {
      PROMETHEUS_URL: process.env.PROMETHEUS_URL ?? "http://localhost:9090",
      LOKI_URL: process.env.LOKI_URL ?? "http://localhost:3100",
      QUERY_TIMEOUT_MS: "20000",
      REVALIDATE_SECONDS: "30",
    },
  },
});
