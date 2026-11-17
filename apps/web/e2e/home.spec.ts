import { expect, test } from "@playwright/test";

test("home page shows API: ok when the API is running", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API: ok")).toBeVisible();
});
