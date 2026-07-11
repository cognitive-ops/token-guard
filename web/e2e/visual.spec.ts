import { test, expect } from "@playwright/test";

/**
 * Visual regression tests. Each dashboard is captured in light AND dark and
 * compared to a committed baseline, so UI/UX regressions (layout, color,
 * theming) are caught. Baselines: `npx playwright test visual.spec.ts
 * --update-snapshots`. Charts are masked (canvas pixels vary run-to-run with
 * live data); we assert the surrounding layout/chrome.
 */
const PAGES: Array<[string, string]> = [
  ["overview", "/overview"],
  ["real-cost", "/real-cost"],
  ["usage-patterns", "/usage-patterns"],
  ["developer", "/developer"],
];

for (const theme of ["light", "dark"] as const) {
  for (const [name, path] of PAGES) {
    test(`visual: ${name} (${theme})`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto(path, { waitUntil: "networkidle" });
      // Let streamed sections + charts settle.
      await page.waitForTimeout(3500);
      await expect(page).toHaveScreenshot(`${name}-${theme}.png`, {
        fullPage: true,
        // Charts render to <canvas> with live, time-varying data → mask them.
        mask: [page.locator("canvas")],
        maxDiffPixelRatio: 0.02,
        animations: "disabled",
      });
    });
  }
}
