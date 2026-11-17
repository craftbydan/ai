import { expect, test } from "@playwright/test";
import fs from "node:fs";
import { CARD, HAND_PAGE, API, ensureHand, newChat, newChatWithCard, newChatWithRender } from "./helpers";

test.describe.configure({ mode: "serial" });

test("(a) uploading handwriting with the tick box makes the hand ready", async ({ page }) => {
  await page.goto("/hand");
  await page.locator('input[type="file"]').setInputFiles(HAND_PAGE);
  await page.getByLabel(/This is my own handwriting/).check();
  await page.getByRole("button", { name: "Upload this page" }).click();
  await expect(page.locator('[data-status="ready"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("sample-count")).not.toHaveText(/^0 /);
});

test("(b) a chat with a card and 'write happy birthday' shows a preview", async ({
  page,
  request,
}) => {
  await ensureHand(request);
  await page.goto("/chats");
  await expect(page.getByRole("heading", { name: "Your chats" })).toBeVisible();
  await page.getByRole("button", { name: "New chat" }).click();
  await page.waitForURL(/\/chats\/[^/]+$/);
  await page.locator('input[name="chat-file"]').setInputFiles(CARD);
  await expect(page.getByTestId("page-image")).toBeVisible();
  await page.getByLabel("What should it write, and where?").fill("write happy birthday");
  await page.getByRole("button", { name: "Send" }).click();
  const preview = page.getByTestId("preview-image");
  await expect(preview).toBeVisible();
  await expect
    .poll(() => preview.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
    .toBe(true);
  await expect(page.getByRole("log").getByText("write happy birthday")).toBeVisible();
});

test("region overlay toggles from the analysis endpoint", async ({ page, request }) => {
  const id = await newChatWithRender(request);
  await page.goto(`/chats/${id}`);
  await page.getByRole("button", { name: "Show writable areas" }).click();
  await expect(page.getByTestId("region-overlay")).toBeVisible();
  await page.getByRole("button", { name: "Hide writable areas" }).click();
  await expect(page.getByTestId("region-overlay")).toHaveCount(0);
});

test("(c) Export PDF downloads a marked PDF", async ({ page, request }) => {
  const id = await newChatWithRender(request);
  await page.goto(`/chats/${id}`);
  await expect(page.getByTestId("preview-image")).toBeVisible();
  await expect(page.getByTestId("ai-note")).toContainText("AI-generated");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export PDF" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  const file = await download.path();
  expect(fs.readFileSync(file).subarray(0, 4).toString()).toBe("%PDF");
});

test("(d) uploading handwriting without the tick box shows an error and sends no file", async ({
  page,
}) => {
  const uploads: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/hand/documents")) uploads.push(r.method());
  });
  await page.goto("/hand");
  await page.locator('input[type="file"]').setInputFiles(HAND_PAGE);
  await page.getByRole("button", { name: "Upload this page" }).click();
  await expect(page.getByTestId("hand-form-error")).toContainText("tick the box");
  expect(uploads).toEqual([]);
});

test("(e) a file classified as an exam shows the refusal notice", async ({ page, request }) => {
  const id = await newChat(request);
  // Test-only switch: the API (running CLASSIFIER=mock:ok) honours this header per request.
  await page.route(`${API}/chats/${id}/files`, (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-test-classifier": "mock:exam" } }),
  );
  await page.goto(`/chats/${id}`);
  await page.locator('input[name="chat-file"]').setInputFiles(CARD);
  const notice = page.getByTestId("notice-refusal");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("exam");
  await expect(page.getByRole("button", { name: "Export PDF" })).toBeDisabled();
});

test("keyboard only: Tab to the composer and Enter sends", async ({ page, request }) => {
  await ensureHand(request);
  const id = await newChatWithCard(request);
  await page.goto(`/chats/${id}`);
  await expect(page.getByTestId("page-image")).toBeVisible();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(() => document.activeElement?.id === "composer")) break;
  }
  await expect(page.locator("#composer")).toBeFocused();
  await page.keyboard.type("write thank you");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("log").getByText("write thank you")).toBeVisible();
  await expect(page.getByTestId("preview-image")).toBeVisible();
});
