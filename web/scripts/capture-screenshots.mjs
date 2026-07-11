// Capture presentational full-page screenshots of every dashboard view for the
// README / PR. Run against a server with AUTH disabled:
//
//   AUTH_ENABLED=false PROMETHEUS_URL=... LOKI_URL=... ADMIN_KEY_PATH=... \
//     npx next start -p 3026 &
//   BASE_URL=http://localhost:3026 node scripts/capture-screenshots.mjs
//
// Charts render to <canvas>; we wait for them to paint before shooting.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:3026";
const OUT = new URL("../screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const SHOTS = [
  { name: "overview", path: "/overview", theme: "light" },
  { name: "overview-dark", path: "/overview", theme: "dark" },
  { name: "real-cost", path: "/real-cost", theme: "light" },
  { name: "usage-patterns", path: "/usage-patterns", theme: "light" },
  { name: "developer", path: "/developer", theme: "light" },
  { name: "api-cost", path: "/api-cost", theme: "light" },
];

const browser = await chromium.launch({ channel: "chrome" });
try {
  for (const s of SHOTS) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.addInitScript((t) => localStorage.setItem("theme", t), s.theme);
    // networkidle is unreliable on data-heavy pages (many backend queries) — use
    // DOM-ready, then explicitly wait for charts to paint and settle.
    await page.goto(BASE + s.path, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForSelector("canvas", { timeout: 45_000 }).catch(() => {});
    await page.waitForTimeout(4000);
    await page.screenshot({ path: `${OUT}${s.name}.png`, fullPage: true });
    await ctx.close();
    console.log("captured", s.name);
  }
} finally {
  await browser.close();
}
