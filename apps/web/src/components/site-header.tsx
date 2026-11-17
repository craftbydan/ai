"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";

const NAV = [
  { href: "/hand", label: "Your hand" },
  { href: "/chats", label: "Chats" },
];

const ITEM =
  "inline-flex min-h-[44px] items-center rounded-control px-3 text-[0.9375rem] font-semibold text-ink-mid hover:bg-paper-well hover:text-ink";

export function SiteHeader() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  return (
    <header className="border-b border-hairline">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
        <Link href="/" className="hand text-[2rem] leading-none text-ink">
          handwriting<span className="text-margin">.</span>ai
        </Link>
        <nav aria-label="Main">
          <ul className="flex flex-wrap items-center gap-1">
            {user
              ? NAV.map((n) => (
                  <li key={n.href}>
                    <Link href={n.href} className={ITEM}>
                      {n.label}
                    </Link>
                  </li>
                ))
              : null}
            {loading ? null : user ? (
              <>
                <li
                  data-testid="account-email"
                  className="max-w-[12rem] truncate px-2 text-[0.8125rem] text-ink-low"
                  title={user.email}
                >
                  {user.email}
                </li>
                <li>
                  <button
                    type="button"
                    className={ITEM}
                    onClick={() => void logout().then(() => router.push("/login"))}
                  >
                    Log out
                  </button>
                </li>
              </>
            ) : (
              <>
                <li>
                  <Link href="/login" className={ITEM}>
                    Log in
                  </Link>
                </li>
                <li>
                  <Link href="/signup" className="btn btn-primary">
                    Sign up
                  </Link>
                </li>
              </>
            )}
          </ul>
        </nav>
      </div>
    </header>
  );
}
