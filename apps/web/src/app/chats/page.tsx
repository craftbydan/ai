"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Notice } from "@/components/notice";
import { createChat, errorMessage, listChats } from "@/lib/api";
import type { Chat } from "@/lib/api";

function when(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function ChatsPage() {
  const router = useRouter();
  const [chats, setChats] = useState<Chat[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let alive = true;
    listChats()
      .then((c) => alive && setChats(c))
      .catch((e: unknown) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  async function start() {
    setCreating(true);
    setError(null);
    try {
      const chat = await createChat();
      router.push(`/chats/${chat.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setCreating(false);
    }
  }

  return (
    <main id="main" className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:py-14">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="hand text-[length:var(--hand-lg)] text-ink">Your chats</h1>
        <button className="btn btn-primary" onClick={() => void start()} disabled={creating}>
          {creating ? "Opening…" : "New chat"}
        </button>
      </div>
      <p className="mt-2 text-ink-mid">
        Each chat is one card, letter or page. Add the file, say what to write, and keep tweaking.
      </p>

      {error ? (
        <div className="mt-6">
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      <div className="mt-8">
        {chats === null && !error ? (
          <div className="grid gap-3" aria-label="Loading chats">
            <div className="skeleton h-16" />
            <div className="skeleton h-16" />
          </div>
        ) : chats !== null && chats.length === 0 ? (
          <div data-testid="chats-empty" className="sheet ruled relative px-8 py-10">
            <span aria-hidden="true" className="absolute inset-y-0 left-6 w-px bg-margin/70" />
            <p className="hand pl-4 text-[2.2rem] text-ink">No chats yet.</p>
            <p className="mt-2 pl-4 text-ink-mid">
              Start one with a birthday card or a planner page. Your handwriting needs to be ready
              first, so if you have not added a page,{" "}
              <Link href="/hand" className="link">
                do that now
              </Link>
              .
            </p>
          </div>
        ) : (
          <ul className="grid gap-3">
            {chats?.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/chats/${c.id}`}
                  className="sheet flex min-h-[44px] items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-paper-1"
                >
                  <span className="hand text-[1.7rem] text-ink">{c.title || "Untitled chat"}</span>
                  <span className="text-[0.875rem] text-ink-mid">{when(c.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
