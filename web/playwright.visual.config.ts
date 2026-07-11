import { defineConfig, devices } from "@playwright/test";

/** Visual-regression config: runs only visual.spec.ts against a normal server. */
const PORT = Number(process.env.E2E_VISUAL_PORT ?? 3026);
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /visual\.spec\.ts/,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000, toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  use: { baseURL: BASE_URL },
  projects: [{ name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } }],
  webServer: {
    command: `npx next start -p ${PORT}`,
    url: `${BASE_URL}/api/health`,
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
    env: {
      PROMETHEUS_URL: process.env.PROMETHEUS_URL ?? "http://localhost:9090",
      LOKI_URL: process.env.LOKI_URL ?? "http://localhost:3100",
      QUERY_TIMEOUT_MS: "20000",
    },
  },
});
