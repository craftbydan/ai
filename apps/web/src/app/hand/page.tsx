"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { FileDrop } from "@/components/file-drop";
import { Notice } from "@/components/notice";
import { StatusChip } from "@/components/status-chip";
import { errorMessage, uploadHandDocument } from "@/lib/api";
import type { HandDocument } from "@/lib/api";
import { useHand } from "@/lib/hooks";

const FALLBACK_STATEMENT =
  "Only upload your own handwriting. The app learns from your own hand and never from anyone else's.";

function docLabel(d: HandDocument, learning: boolean): { text: string; busy: boolean } {
  if (d.status === "done") return { text: "Learned", busy: false };
  if (d.status === "failed") return { text: "Could not read this page", busy: false };
  return { text: learning ? "Reading your letters" : "Queued", busy: true };
}

export default function HandPage() {
  const { data: hand, error, loading, refresh } = useHand();
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!confirmed) {
      setFormError("Please tick the box to confirm this is your own handwriting. Nothing was uploaded.");
      return;
    }
    if (!file) {
      setFormError("Choose a photo or scan of your handwriting first.");
      return;
    }
    setBusy(true);
    try {
      await uploadHandDocument(file, confirmed);
      setFile(null);
      form.current?.reset();
      setConfirmed(false);
      await refresh();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const status = hand?.status ?? "empty";
  const learning = status === "learning";
  const docs = hand?.documents ?? [];

  return (
    <main id="main" className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:py-14">
      <div className="grid gap-10 lg:grid-cols-[1fr_22rem] lg:gap-16">
        <section aria-labelledby="hand-title">
          <h1 id="hand-title" className="hand text-[length:var(--hand-lg)] text-ink">
            Show us how you write
          </h1>
          <p className="mt-3 max-w-[36rem] text-ink-mid">
            A page with a few lines of normal writing is enough. Use good light, keep the page flat
            and fill it with your own words, any words. JPG, PNG or PDF, up to a few pages.
          </p>

          <form ref={form} onSubmit={onSubmit} noValidate className="mt-8 grid max-w-[36rem] gap-5">
            <FileDrop
              accept="image/png,image/jpeg,application/pdf"
              file={file}
              onFile={(f) => {
                setFile(f);
                setFormError(null);
              }}
              prompt="Drop a page here, or choose one"
              hint="Photo, scan or PDF of your own handwriting"
              disabled={busy}
            />
            <div className="flex items-start gap-3">
              <input
                id="own-hand"
                type="checkbox"
                checked={confirmed}
                onChange={(e) => {
                  setConfirmed(e.target.checked);
                  setFormError(null);
                }}
                className="mt-1 size-5 shrink-0 accent-[var(--pen)]"
              />
              <label htmlFor="own-hand" className="text-[0.9375rem] text-ink">
                <span className="font-semibold">This is my own handwriting.</span>{" "}
                {hand?.own_hand_statement ?? FALLBACK_STATEMENT}
              </label>
            </div>
            {formError ? (
              <Notice tone="error" testId="hand-form-error">
                {formError}
              </Notice>
            ) : null}
            <div>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "Uploading…" : "Upload this page"}
              </button>
            </div>
          </form>
        </section>

        <aside aria-labelledby="status-title" className="sheet h-fit p-5">
          <h2 id="status-title" className="hand text-[1.9rem] text-ink">
            Your hand so far
          </h2>
          {loading && !hand ? (
            <div className="mt-4 grid gap-3" aria-label="Loading your hand">
              <div className="skeleton h-8 w-40" />
              <div className="skeleton h-16 w-full" />
            </div>
          ) : error && !hand ? (
            <div className="mt-4">
              <Notice tone="error">{error}</Notice>
              <button className="btn btn-quiet mt-3" onClick={() => void refresh()}>
                Try again
              </button>
            </div>
          ) : (
            <>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <StatusChip status={status} />
                <span className="text-[0.875rem] text-ink-mid" data-testid="sample-count">
                  {hand?.sample_count ?? 0} word samples
                </span>
              </div>
              {status === "failed" && hand?.status_message ? (
                <div className="mt-4">
                  <Notice tone="error">{hand.status_message}</Notice>
                </div>
              ) : null}
              {docs.length === 0 ? (
                <p className="mt-5 text-[0.9375rem] text-ink-mid" data-testid="docs-empty">
                  No pages yet. Once you upload one, you can watch it being learned here.
                </p>
              ) : (
                <ul className="mt-5 grid gap-3" aria-label="Uploaded pages">
                  {docs.map((d, i) => {
                    const l = docLabel(d, learning);
                    return (
                      <li key={d.id} className="rounded-control border border-hairline p-3">
                        <div className="flex items-baseline justify-between gap-3 text-[0.9375rem]">
                          <span className="font-semibold">Page set {i + 1}</span>
                          <span className="text-ink-mid">
                            {d.page_count} {d.page_count === 1 ? "page" : "pages"}
                          </span>
                        </div>
                        <p className="mt-1 text-[0.875rem] text-ink-mid">{l.text}</p>
                        {l.busy ? (
                          <div
                            role="progressbar"
                            aria-label="Learning progress"
                            className="mt-2 h-1.5 overflow-hidden rounded-full bg-paper-well"
                          >
                            <div className="skeleton h-full w-full !rounded-full !bg-pen/40" />
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
              {status === "ready" ? (
                <Link href="/chats" className="btn btn-primary mt-5 w-full">
                  Start writing
                </Link>
              ) : null}
            </>
          )}
        </aside>
      </div>
    </main>
  );
}
