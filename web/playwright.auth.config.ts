import { defineConfig, devices } from "@playwright/test";

/**
 * Auth-on E2E config: boots a second server with AUTH_ENABLED=true and the
 * local break-glass login, on its own port, and runs only the auth spec.
 */
const PORT = Number(process.env.E2E_AUTH_PORT ?? 3025);
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /auth\.spec\.ts/,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: { baseURL: BASE_URL, trace: "retain-on-failure" },
  projects: [
    { name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } },
  ],
  webServer: {
    command: `npx next start -p ${PORT}`,
    url: `${BASE_URL}/login`,
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
    env: {
      PROMETHEUS_URL: process.env.PROMETHEUS_URL ?? "http://localhost:9090",
      LOKI_URL: process.env.LOKI_URL ?? "http://localhost:3100",
      AUTH_ENABLED: "true",
      AUTH_SECRET: "e2e-test-secret-not-for-production",
      LOCAL_LOGIN_ENABLED: "true",
      LOCAL_USERNAME: "admin",
      LOCAL_PASSWORD: "admin",
    },
  },
});
