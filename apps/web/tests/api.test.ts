import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getHealth } from "../src/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetch(impl: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

describe("getHealth", () => {
  it("returns the parsed health body", async () => {
    mockFetch(async () =>
      Response.json({ status: "ok", renderer: "fake", ocr: "fake" }),
    );
    await expect(getHealth()).resolves.toEqual({ status: "ok", renderer: "fake", ocr: "fake" });
  });

  it("maps the standard error shape to ApiError", async () => {
    mockFetch(async () =>
      Response.json({ error: { code: "internal", message: "Something went wrong" } }, { status: 500 }),
    );
    const err = await getHealth().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "internal", message: "Something went wrong", status: 500 });
  });

  it("gives a readable error when the API is unreachable", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const err = await getHealth().catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "network", status: 0 });
    expect((err as ApiError).message).toMatch(/cannot reach the API/i);
  });

  it("handles non-JSON error responses", async () => {
    mockFetch(async () => new Response("<html>bad gateway</html>", { status: 502 }));
    const err = await getHealth().catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "unknown", status: 502 });
  });
});
