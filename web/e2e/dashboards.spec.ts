import { test, expect } from "@playwright/test";

test.describe("Shell, navigation & controls", () => {
  test("root redirects to overview", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/overview/);
  });

  test("overview renders KPIs", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByText("Total Cost", { exact: true })).toBeVisible();
    await expect.poll(() => page.locator("canvas").count(), { timeout: 20_000 }).toBeGreaterThan(0);
  });

  test("nav tabs switch dashboards", async ({ page }) => {
    await page.goto("/overview");
    // Tabs render twice (desktop + responsive); take the first.
    await page.getByRole("link", { name: "Usage Patterns" }).first().click();
    await expect(page).toHaveURL(/\/usage-patterns/);
    await expect(page.getByText("Engagement leaderboard")).toBeVisible();
  });

  test("time picker changes the range via the URL", async ({ page }) => {
    await page.goto("/real-cost?range=30d");
    await page.getByRole("button", { name: "Time range" }).click();
    await page.getByRole("menuitem", { name: "7 days", exact: true }).click();
    await expect(page).toHaveURL(/range=7d/);
  });

  test("theme switcher toggles dark/light", async ({ page }) => {
    await page.goto("/overview");
    await page.getByRole("button", { name: "Theme" }).click();
    await page.getByRole("menuitem", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveClass(/light/);
    await page.getByRole("button", { name: "Theme" }).click();
    await page.getByRole("menuitem", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("api-cost page loads with a month picker", async ({ page }) => {
    await page.goto("/api-cost");
    await expect(page.getByRole("heading", { name: "API Cost", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Month" })).toBeVisible();
    // Without an Admin key (CI/e2e) it shows the not-configured panel rather than erroring.
    await expect(page.getByText(/Admin API key not configured|Cost by client/)).toBeVisible();
  });

  test("info (i) button explains a metric", async ({ page }) => {
    await page.goto("/overview");
    await page.getByRole("button", { name: /^About:/ }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Source")).toBeVisible();
    await expect(dialog.getByText("How it's calculated")).toBeVisible();
  });
});

test.describe("Other dashboards render", () => {
  test("usage patterns renders leaderboard and charts", async ({ page }) => {
    await page.goto("/usage-patterns");
    await expect(page.getByText("Engagement leaderboard")).toBeVisible();
    await expect.poll(() => page.locator("canvas").count(), { timeout: 20_000 }).toBeGreaterThan(0);
  });

  test("developer page renders a selected developer with charts", async ({ page }) => {
    await page.goto("/developer", { waitUntil: "domcontentloaded" });
    // Shell + picker paint immediately (fast getUserList).
    await expect(page.getByLabel("Developer")).toBeVisible({ timeout: 20_000 });
    // Charts stream/lazy-mount as their (cached) sections resolve.
    await expect.poll(() => page.locator("canvas").count(), { timeout: 45_000 }).toBeGreaterThan(0);
  });
});
