"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, errorMessage, getMe, logout as apiLogout } from "@/lib/api";
import type { Me } from "@/lib/api";
import { Notice } from "@/components/notice";

interface AuthState {
  user: Me | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setUser(await getMe());
      setError(null);
    } catch (err) {
      setUser(null);
      // 401 just means "not logged in"; anything else is worth telling the person.
      setError(err instanceof ApiError && err.status === 401 ? null : errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getMe()
      .then((me) => alive && (setUser(me), setError(null)))
      .catch((err: unknown) => {
        if (!alive) return;
        setUser(null);
        setError(err instanceof ApiError && err.status === 401 ? null : errorMessage(err));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, error, refresh, logout }),
    [user, loading, error, refresh, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

const PROTECTED = ["/hand", "/chats"];

export function isProtectedPath(path: string): boolean {
  return PROTECTED.some((p) => path === p || path.startsWith(`${p}/`));
}

/** Only follow same-site relative paths after login (no open redirect). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/chats";
}

/** Sends logged-out visitors of protected pages to /login (and back afterwards). */
export function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading, error } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const protectedPage = isProtectedPath(pathname);

  useEffect(() => {
    if (protectedPage && !loading && !user && !error) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [protectedPage, loading, user, error, pathname, router]);

  if (!protectedPage || user) return <>{children}</>;
  if (error && !loading) {
    return (
      <main id="main" className="mx-auto max-w-xl px-4 py-14 sm:px-6">
        <Notice tone="error">{error}</Notice>
      </main>
    );
  }
  return (
    <main id="main" className="mx-auto max-w-6xl px-4 py-10 sm:px-6" aria-busy="true">
      <div className="skeleton h-10 w-64" />
    </main>
  );
}
