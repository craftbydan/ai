import { describe, expect, it } from "vitest";
import { isProtectedPath, safeNext } from "../src/components/auth";

describe("auth paths", () => {
  it("protects the hand and chat pages only", () => {
    expect(["/hand", "/chats", "/chats/abc"].every(isProtectedPath)).toBe(true);
    expect(["/", "/login", "/signup", "/handy"].some(isProtectedPath)).toBe(false);
  });

  it("only follows same-site relative next paths", () => {
    expect(safeNext("/chats/abc")).toBe("/chats/abc");
    expect(safeNext("//evil.example")).toBe("/chats");
    expect(safeNext("https://evil.example")).toBe("/chats");
    expect(safeNext(null)).toBe("/chats");
  });
});
