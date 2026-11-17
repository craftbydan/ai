import { expect, test } from "@playwright/test";

// Runs in its own phase (E2E_PHASE=auth) against an API with DEV_USER=0: real accounts only.
test("signup, then log out, then log in again", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "a long enough password";

  // Protected pages send a logged-out visitor to /login.
  await page.goto("/chats");
  await page.waitForURL(/\/login/);

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();
  await page.waitForURL(/\/chats$/);
  await expect(page.getByTestId("account-email")).toHaveText(email);
  await expect(page.getByRole("heading", { name: "Your chats" })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await page.waitForURL(/\/login/);
  await expect(page.getByTestId("account-email")).toHaveCount(0);
  await page.goto("/chats");
  await page.waitForURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("the wrong password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("auth-error")).toContainText("not right");

  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL(/\/chats$/);
  await expect(page.getByTestId("account-email")).toHaveText(email);
});
