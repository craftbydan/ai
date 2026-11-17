import { expect, test } from "@playwright/test";
import { ensureHand, newChatWithRender } from "./helpers";

for (const width of [390, 1440]) {
  test(`no horizontal scrollbar at ${width}px`, async ({ page, request }) => {
    await ensureHand(request);
    const id = await newChatWithRender(request);
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/hand", "/chats", `/chats/${id}`]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const [scroll, client] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scroll, `${path} at ${width}px`).toBeLessThanOrEqual(client);
    }
  });
}

test("empty states are designed on /chats and an empty chat", async ({ page, request }) => {
  const res = await request.post("http://localhost:8000/chats");
  const { id } = await res.json();
  await page.goto(`/chats/${id}`);
  await expect(page.getByTestId("preview-empty")).toBeVisible();
  await expect(page.getByTestId("messages-empty")).toBeVisible();
});
