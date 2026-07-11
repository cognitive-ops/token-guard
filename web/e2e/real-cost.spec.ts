import { test, expect } from "@playwright/test";

test.describe("Real Cost dashboard", () => {
  test("renders the shell, logo, and header", async ({ page }) => {
    await page.goto("/real-cost");
    await expect(page.getByRole("banner").getByRole("img", { name: "Token Guard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Real Cost/i, level: 1 })).toBeVisible();
  });

  test("shows headline KPIs with values", async ({ page }) => {
    await page.goto("/real-cost");
    for (const label of ["Org Real Cost", "Service Billed", "OTEL Estimate", "Active Users"]) {
      await expect(page.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(page.getByText(/\$[0-9,]+/).first()).toBeVisible();
  });

  test("renders the per-developer cost table with rows", async ({ page }) => {
    await page.goto("/real-cost");
    const table = page.locator("section", { hasText: "Real Cost per Developer" }).locator("table");
    await expect(table.locator("tbody tr").first()).toBeVisible();
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(3);
  });

  test("lazy-loads chart canvases", async ({ page }) => {
    await page.goto("/real-cost");
    await expect(page.locator("canvas").first()).toBeVisible();
    // Charts stream + lazy-mount; poll until more than one is present.
    await expect.poll(() => page.locator("canvas").count(), { timeout: 20_000 }).toBeGreaterThan(1);
  });

  test("health endpoint returns ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    expect(await res.json()).toEqual({ status: "ok" });
  });
});
