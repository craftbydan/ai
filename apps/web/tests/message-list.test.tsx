import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MessageList, toDisplayMessages } from "../src/components/message-list";
import type { ChatMessage } from "../src/lib/api";

function msg(id: string, role: ChatMessage["role"], content: ChatMessage["content_json"]): ChatMessage {
  return { id, role, content_json: content, created_at: "2026-11-17T10:00:00" };
}

describe("toDisplayMessages", () => {
  it("keeps user text and assistant replies and drops tool rows", () => {
    const out = toDisplayMessages([
      msg("1", "user", { text: "write happy birthday" }),
      msg("2", "assistant", { reply: "" }),
      msg("3", "tool", {}),
      msg("4", "assistant", { reply: "Done." }),
    ]);
    expect(out).toEqual([
      { id: "1", role: "user", text: "write happy birthday" },
      { id: "4", role: "assistant", text: "Done." },
    ]);
  });
});

describe("MessageList", () => {
  it("shows a designed empty state with no messages", () => {
    const html = renderToStaticMarkup(<MessageList messages={[]} />);
    expect(html).toContain("Nothing written yet.");
    expect(html).toContain('data-testid="messages-empty"');
  });

  it("renders each message with its role and marks pending ones", () => {
    const html = renderToStaticMarkup(
      <MessageList
        messages={[
          { id: "a", role: "user", text: "write hello", pending: true },
          { id: "b", role: "assistant", text: "Done." },
        ]}
        thinking
      />,
    );
    expect(html).toContain('data-role="user"');
    expect(html).toContain('data-pending="true"');
    expect(html).toContain("write hello");
    expect(html).toContain('data-role="assistant"');
    expect(html).toContain('data-testid="thinking"');
  });
});
