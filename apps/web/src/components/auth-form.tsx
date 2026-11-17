"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth, safeNext } from "@/components/auth";
import { Notice } from "@/components/notice";
import { errorMessage, login, signup } from "@/lib/api";

const FIELD =
  "min-h-[44px] w-full rounded-control border border-hairline-strong bg-sheet px-3 text-ink";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSignup = mode === "signup";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (isSignup && password.length < 10) {
      setError("Please choose a password of at least 10 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await (isSignup ? signup(email, password) : login(email, password));
      await refresh();
      router.push(safeNext(new URLSearchParams(window.location.search).get("next")));
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main id="main" className="mx-auto max-w-md px-4 py-10 sm:px-6 lg:py-14">
      <h1 className="hand text-[length:var(--hand-lg)] text-ink">
        {isSignup ? "Make an account" : "Welcome back"}
      </h1>
      <p className="mt-2 text-ink-mid">
        {isSignup
          ? "Your handwriting and chats are private to your account."
          : "Log in to see your handwriting and chats."}
      </p>
      <form onSubmit={onSubmit} className="mt-8 grid gap-5" aria-label={isSignup ? "Sign up" : "Log in"}>
        <div className="grid gap-1.5">
          <label htmlFor="email" className="text-[0.9375rem] font-semibold text-ink">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={FIELD}
          />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor="password" className="text-[0.9375rem] font-semibold text-ink">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={isSignup ? "new-password" : "current-password"}
            required
            minLength={isSignup ? 10 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={FIELD}
          />
          {isSignup ? <p className="text-[0.8125rem] text-ink-mid">At least 10 characters.</p> : null}
        </div>
        {error ? (
          <Notice tone="error" testId="auth-error">
            {error}
          </Notice>
        ) : null}
        <div className="flex flex-wrap items-center gap-4">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "One moment…" : isSignup ? "Sign up" : "Log in"}
          </button>
          <Link href={isSignup ? "/login" : "/signup"} className="link text-[0.9375rem] font-semibold">
            {isSignup ? "Already have an account? Log in" : "New here? Sign up"}
          </Link>
        </div>
      </form>
    </main>
  );
}
