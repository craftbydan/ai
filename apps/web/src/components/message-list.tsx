import type { ChatMessage } from "@/lib/api";

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  pending?: boolean;
}

/** Keep only what a person should read: user text and assistant replies (no tool rows). */
export function toDisplayMessages(messages: ChatMessage[]): DisplayMessage[] {
  const out: DisplayMessage[] = [];
  for (const m of messages) {
    const c = m.content_json ?? {};
    if (m.role === "user" && c.text) out.push({ id: m.id, role: "user", text: c.text });
    else if (m.role === "assistant" && c.reply) out.push({ id: m.id, role: "assistant", text: c.reply });
  }
  return out;
}

export function MessageList({
  messages,
  thinking = false,
}: {
  messages: DisplayMessage[];
  thinking?: boolean;
}) {
  if (messages.length === 0 && !thinking) {
    return (
      <div data-testid="messages-empty" className="px-2 py-6">
        <p className="hand text-[2rem] text-ink">Nothing written yet.</p>
        <p className="mt-2 text-[0.9375rem] text-ink-mid">
          Add a card or page, then say what to write. Try &ldquo;write happy birthday in the
          middle&rdquo; or &ldquo;make it a little bigger&rdquo;.
        </p>
      </div>
    );
  }
  return (
    <ol className="flex flex-col gap-3" aria-label="Conversation">
      {messages.map((m) => (
        <li
          key={m.id}
          data-role={m.role}
          data-pending={m.pending ? "true" : undefined}
          className={`rise max-w-[88%] rounded-surface px-4 py-3 text-[0.9375rem] ${
            m.role === "user"
              ? "self-end bg-pen-quiet text-ink"
              : "self-start border border-hairline bg-paper-well text-ink"
          } ${m.pending ? "opacity-70" : ""}`}
        >
          <span className="sr-only">{m.role === "user" ? "You: " : "Assistant: "}</span>
          {m.text}
        </li>
      ))}
      {thinking ? (
        <li
          data-testid="thinking"
          className="self-start rounded-surface border border-hairline bg-paper-well px-4 py-3 text-[0.9375rem] text-ink-mid"
        >
          Writing it out&hellip;
        </li>
      ) : null}
    </ol>
  );
}
