import { expect } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const FIXTURES = path.resolve(__dirname, "../../../services/api/tests/fixtures");
export const HAND_PAGE = path.join(FIXTURES, "hand_page_1.png");
export const CARD = path.join(FIXTURES, "card.pdf");

function filePart(file: string, mime: string) {
  return { name: path.basename(file), mimeType: mime, buffer: fs.readFileSync(file) };
}

/** Make sure the dev user has a ready hand (uses the API, not the UI). */
export async function ensureHand(request: APIRequestContext): Promise<void> {
  const current = await (await request.get(`${API}/hand`)).json();
  if (current.status !== "ready") {
    const res = await request.post(`${API}/hand/documents`, {
      multipart: { file: filePart(HAND_PAGE, "image/png"), own_hand_confirmed: "true" },
    });
    expect(res.status()).toBe(201);
  }
  await expect
    .poll(async () => (await (await request.get(`${API}/hand`)).json()).status, { timeout: 30_000 })
    .toBe("ready");
}

export async function newChat(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API}/chats`);
  expect(res.status()).toBe(201);
  return (await res.json()).id as string;
}

export async function newChatWithCard(request: APIRequestContext): Promise<string> {
  const id = await newChat(request);
  const up = await request.post(`${API}/chats/${id}/files`, {
    multipart: { file: filePart(CARD, "application/pdf") },
  });
  expect(up.status()).toBe(201);
  return id;
}

export async function newChatWithRender(request: APIRequestContext): Promise<string> {
  await ensureHand(request);
  const id = await newChatWithCard(request);
  const res = await request.post(`${API}/chats/${id}/messages`, {
    data: { text: "write happy birthday" },
  });
  expect(res.status()).toBe(200);
  return id;
}
