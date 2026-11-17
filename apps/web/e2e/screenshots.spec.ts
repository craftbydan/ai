import { test } from "@playwright/test";
import { ensureHand, newChatWithRender } from "./helpers";

// Run on demand: SCREENSHOTS=/some/dir npx playwright test e2e/screenshots.spec.ts
const dir = process.env.SCREENSHOTS;

test.skip(!dir, "set SCREENSHOTS=<dir> to capture screenshots");

for (const width of [390, 1440]) {
  test(`screenshots at ${width}px`, async ({ browser, request }) => {
    await ensureHand(request);
    const id = await newChatWithRender(request);
    const ctx = await browser.newContext({
      viewport: { width, height: width === 390 ? 844 : 900 },
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    for (const [name, path] of [
      ["home", "/"],
      ["hand", "/hand"],
      ["chat", `/chats/${id}`],
    ] as const) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${dir}/${name}-${width}.png`, fullPage: true });
    }
    await ctx.close();
  });
}
