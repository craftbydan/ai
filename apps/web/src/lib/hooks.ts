"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getChat, getHand, errorMessage } from "./api";
import type { ChatDetail, Hand } from "./api";

export interface Polled<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

/** Fetch once, then re-fetch every `intervalMs` while `shouldPoll(data)` is true.
    `fetcher` and `shouldPoll` must be referentially stable. */
function usePolled<T>(
  fetcher: () => Promise<T>,
  shouldPoll: (data: T) => boolean,
  intervalMs: number,
): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async (): Promise<void> => {
      if (timer) clearTimeout(timer);
      try {
        const next = await fetcher();
        if (!alive) return;
        setData(next);
        setError(null);
        if (shouldPoll(next)) timer = setTimeout(() => void run(), intervalMs);
      } catch (err) {
        if (!alive) return;
        setError(errorMessage(err));
        timer = setTimeout(() => void run(), intervalMs * 3);
      } finally {
        if (alive) setLoading(false);
      }
    };
    reload.current = run;
    void run();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [fetcher, shouldPoll, intervalMs]);

  const refresh = useCallback(() => reload.current(), []);
  return { data, error, loading, refresh };
}

const handNeedsPolling = (h: Hand): boolean => h.status === "learning";

/** Hand status: polls every 1.5 s while the profile is being learned. */
export function useHand(): Polled<Hand> {
  return usePolled(getHand, handNeedsPolling, 1500);
}

/** Polls while the newest message is the user's and has no reply yet (a render is in flight),
    so a new preview shows up as soon as `latest_render_version` changes. */
const chatNeedsPolling = (c: ChatDetail): boolean =>
  c.messages.filter((m) => m.role !== "tool").at(-1)?.role === "user";

export function useChat(id: string): Polled<ChatDetail> {
  const fetcher = useCallback(() => getChat(id), [id]);
  return usePolled(fetcher, chatNeedsPolling, 1500);
}
