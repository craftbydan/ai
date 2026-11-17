"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";

export function Composer({
  onSend,
  busy,
}: {
  onSend: (text: string) => Promise<boolean>;
  busy: boolean;
}) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  async function submit() {
    const value = text.trim();
    if (!value || busy) return;
    setText("");
    const ok = await onSend(value);
    if (!ok) setText(value);
    area.current?.focus();
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="grid gap-2"
    >
      <label htmlFor="composer" className="text-[0.875rem] font-semibold text-ink-mid">
        What should it write, and where?
      </label>
      <textarea
        id="composer"
        ref={area}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        rows={2}
        maxLength={2000}
        placeholder="e.g. write happy birthday in the middle of the card"
        className="w-full resize-y rounded-control border border-hairline-strong bg-sheet px-3 py-2 text-[var(--text-base)] text-ink"
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.8125rem] text-ink-low">Enter sends, Shift+Enter adds a line.</p>
        <button type="submit" className="btn btn-primary" disabled={busy || text.trim() === ""}>
          Send
        </button>
      </div>
    </form>
  );
}
