import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { ensureHand, newChatWithCard, newChatWithRender } from "./helpers";

// Zero serious or critical axe violations on every page, in light mode and in dark mode.
async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.passes.length, "axe ran real rules").toBeGreaterThan(10);
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

async function checkBothSchemes(page: Page, url: string, ready: () => Promise<void>) {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto(url);
    await ready();
    expect(await seriousViolations(page), `${url} (${scheme})`).toEqual([]);
  }
}

test("home page has no serious accessibility violations", async ({ page }) => {
  await checkBothSchemes(page, "/", async () => {
    await expect(page.getByText("API: ok")).toBeVisible();
  });
});

test("/hand has no serious accessibility violations", async ({ page, request }) => {
  await ensureHand(request);
  await checkBothSchemes(page, "/hand", async () => {
    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
});

test("/chats has no serious accessibility violations", async ({ page, request }) => {
  await newChatWithCard(request);
  await checkBothSchemes(page, "/chats", async () => {
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
});

test("/chats/[id] has no serious accessibility violations (empty chat, with a render)", async ({
  page,
  request,
}) => {
  const withCard = await newChatWithCard(request);
  await checkBothSchemes(page, `/chats/${withCard}`, async () => {
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
  const withRender = await newChatWithRender(request);
  await checkBothSchemes(page, `/chats/${withRender}`, async () => {
    await expect(page.locator("img").first()).toBeVisible();
  });
});

test("/login has no serious accessibility violations", async ({ page }) => {
  await checkBothSchemes(page, "/login", async () => {
    await expect(page.getByRole("button", { name: /log in|sign in/i })).toBeVisible();
  });
});

test("every informational image has alt text", async ({ page, request }) => {
  const id = await newChatWithRender(request);
  await page.goto(`/chats/${id}`);
  const img = page.locator("img").first();
  await expect(img).toBeVisible();
  const imgs = page.locator("img");
  const count = await imgs.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    expect((await imgs.nth(i).getAttribute("alt")) ?? "", `img #${i}`).not.toBe("");
  }
});
