import { test, expect } from "@playwright/test";

/**
 * Auth flow — runs against a server started with AUTH_ENABLED=true
 * (see playwright.auth.config.ts). Exercises the local break-glass login.
 */
test.describe("Auth (Keycloak + local login)", () => {
  test("protected route redirects unauthenticated users to /login", async ({
    page,
  }) => {
    await page.goto("/real-cost");
    await expect(page).toHaveURL(/\/login/);
    await expect(page).toHaveURL(/callbackUrl/);
  });

  test("login page shows the local sign-in form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("img", { name: "Scopic" })).toBeVisible();
    await expect(page.locator('input[name="username"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Local sign-in/i }),
    ).toBeVisible();
  });

  test("health endpoint stays public when auth is on", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
  });

  test("local login signs in and reaches the dashboard, then signs out", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.locator('input[name="username"]').fill("admin");
    await page.locator('input[name="password"]').fill("admin");
    await page.getByRole("button", { name: /Local sign-in/i }).click();

    await expect(page).toHaveURL(/\/real-cost/);
    await expect(
      page.getByRole("heading", { name: /Real Cost/i, level: 1 }),
    ).toBeVisible();

    // The nav shows the signed-in user + sign-out.
    const signOut = page.getByRole("button", { name: /Sign out/i });
    await expect(signOut).toBeVisible();
    await signOut.click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("wrong credentials are rejected", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[name="username"]').fill("admin");
    await page.locator('input[name="password"]').fill("wrong");
    await page.getByRole("button", { name: /Local sign-in/i }).click();
    await expect(page).toHaveURL(/error=credentials/);
  });
});
