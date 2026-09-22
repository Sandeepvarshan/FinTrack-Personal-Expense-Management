import { expect, test } from "@playwright/test";

test("register, login, and reach the dashboard", async ({ page }) => {
  const email = `e2e-register-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Name").fill("E2E User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("securepass");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Your overview" })).toBeVisible();
});

test("authenticated user can navigate application workflows", async ({ page }) => {
  const email = `e2e-navigation-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Name").fill("Navigation User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("securepass");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your overview" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("securepass");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your overview" })).toBeVisible();
  await page.getByRole("link", { name: "Expenses" }).click();
  await expect(page.getByRole("heading", { name: "Expenses" })).toBeVisible();
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByRole("heading", { name: "Categories" })).toBeVisible();
  await page.getByRole("link", { name: "Budgets" }).click();
  await expect(page.getByRole("heading", { name: "Budgets" })).toBeVisible();
  await page.getByRole("link", { name: "Reports" }).click();
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
  await page.getByRole("link", { name: "Alerts" }).click();
  await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible();
});