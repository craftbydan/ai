"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

type State = { kind: "loading" } | { kind: "ok" } | { kind: "error"; message: string };

export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then(() => {
        if (!cancelled) setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Something went wrong.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "loading") return <p role="status">API: checking…</p>;
  if (state.kind === "ok") return <p role="status">API: ok</p>;
  return (
    <p role="alert" className="text-crit">
      API error: {state.message}
    </p>
  );
}
