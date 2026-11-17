"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { Composer } from "@/components/composer";
import { FileDrop } from "@/components/file-drop";
import { MessageList, toDisplayMessages } from "@/components/message-list";
import type { DisplayMessage } from "@/components/message-list";
import { Notice } from "@/components/notice";
import { PagePreview } from "@/components/page-preview";
import { StatusChip } from "@/components/status-chip";
import {
  errorMessage,
  exportRender,
  filePageUrl,
  isRefusal,
  renderPreviewUrl,
  sendMessage,
  uploadChatFile,
} from "@/lib/api";
import type { ExportFormat } from "@/lib/api";
import { useChat, useHand } from "@/lib/hooks";

interface NoticeState {
  tone: "refusal" | "error";
  text: string;
}

function toNotice(err: unknown): NoticeState {
  return { tone: isRefusal(err) ? "refusal" : "error", text: errorMessage(err) };
}

export default function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: chat, error, loading, refresh } = useChat(id);
  const { data: hand } = useHand();
  const [pending, setPending] = useState<DisplayMessage[]>([]);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [page, setPage] = useState(1);

  const latestFile = chat?.files.at(-1) ?? null;
  const usable = latestFile && latestFile.safety_status === "ok" ? latestFile : null;
  const version = chat?.latest_render_version ?? null;
  const messages = useMemo(
    () => [...toDisplayMessages(chat?.messages ?? []), ...pending],
    [chat?.messages, pending],
  );
  const shownNotice: NoticeState | null =
    notice ??
    (latestFile?.safety_status === "refused" && latestFile.safety_message
      ? { tone: "refusal", text: latestFile.safety_message }
      : null);

  async function onFile(file: File | null) {
    if (!file) return;
    setUploading(true);
    setNotice(null);
    try {
      await uploadChatFile(id, file);
      setPage(1);
    } catch (err) {
      setNotice(toNotice(err));
    } finally {
      setUploading(false);
      await refresh();
    }
  }

  async function onSend(text: string): Promise<boolean> {
    setSending(true);
    setNotice(null);
    setPending([{ id: `pending-${Date.now()}`, role: "user", text, pending: true }]);
    try {
      await sendMessage(id, text);
      await refresh();
      setPending([]);
      return true;
    } catch (err) {
      setPending([]);
      setNotice(toNotice(err));
      await refresh();
      return false;
    } finally {
      setSending(false);
    }
  }

  async function onExport(format: ExportFormat) {
    if (version === null) return;
    setExporting(format);
    setNotice(null);
    try {
      const { blob, filename } = await exportRender(id, version, format, page);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      setNotice(toNotice(err));
    } finally {
      setExporting(null);
    }
  }

  if (loading && !chat) {
    return (
      <main id="main" className="mx-auto max-w-6xl px-4 py-10 sm:px-6" aria-busy="true">
        <div className="grid gap-8 lg:grid-cols-[1.25fr_1fr]">
          <div className="skeleton aspect-[3/4] w-full" />
          <div className="grid h-fit gap-3">
            <div className="skeleton h-10" />
            <div className="skeleton h-24" />
            <div className="skeleton h-24" />
          </div>
        </div>
      </main>
    );
  }

  if (!chat) {
    return (
      <main id="main" className="mx-auto max-w-xl px-4 py-14 sm:px-6">
        <h1 className="hand text-[length:var(--hand-lg)]">We could not open this chat</h1>
        <div className="mt-4">
          <Notice tone="error">{error ?? "This chat does not exist."}</Notice>
        </div>
        <Link href="/chats" className="btn btn-quiet mt-6">
          Back to your chats
        </Link>
      </main>
    );
  }

  const imageUrl = usable
    ? version !== null
      ? renderPreviewUrl(chat.id, version, page)
      : filePageUrl(chat.id, usable.id, page)
    : null;

  return (
    <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/chats" className="link text-[0.875rem] font-semibold">
            All chats
          </Link>
          <h1 className="hand text-[length:var(--hand-lg)] text-ink">Write on your page</h1>
        </div>
        {hand ? <StatusChip status={hand.status} /> : null}
      </div>

      {hand && hand.status !== "ready" ? (
        <div className="mb-6">
          <Notice tone="info" testId="hand-not-ready">
            {hand.status === "learning"
              ? "Still learning your handwriting. You can add your file now; writing starts when it is ready."
              : "Your handwriting is not ready yet, so I cannot write for you. "}
            {hand.status === "learning" ? null : (
              <Link href="/hand" className="link">
                Add a page of your handwriting
              </Link>
            )}
          </Notice>
        </div>
      ) : null}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:gap-10">
        <div className="min-w-0">
          {usable && imageUrl ? (
            <PagePreview
              chatId={chat.id}
              fileId={usable.id}
              imageUrl={imageUrl}
              alt={version !== null ? `Preview, version ${version}` : "Your uploaded page"}
              pageCount={usable.page_count}
              page={Math.min(page, usable.page_count)}
              onPage={setPage}
              isRender={version !== null}
            />
          ) : (
            <div
              data-testid="preview-empty"
              className="sheet ruled relative flex min-h-[22rem] flex-col justify-center px-8 py-10"
            >
              <span aria-hidden="true" className="absolute inset-y-0 left-6 w-px bg-margin/70" />
              <p className="hand pl-4 text-[2.2rem] text-ink">A blank desk.</p>
              <p className="mt-2 max-w-md pl-4 text-ink-mid">
                Add the card, letter or planner page you want written on. It appears here, and the
                preview updates after every change you ask for.
              </p>
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              className="btn btn-primary"
              disabled={version === null || exporting !== null}
              onClick={() => void onExport("pdf")}
            >
              {exporting === "pdf" ? "Preparing PDF…" : "Export PDF"}
            </button>
            <button
              className="btn btn-quiet"
              disabled={version === null || exporting !== null}
              onClick={() => void onExport("png")}
            >
              {exporting === "png" ? "Preparing PNG…" : "Export PNG"}
            </button>
          </div>
          <p className="mt-3 max-w-md text-[0.8125rem] text-ink-mid" data-testid="ai-note">
            Exports carry an AI-generated mark: a small footer on the page and a label in the file
            data. This is by design and cannot be switched off.
          </p>
        </div>

        <section aria-label="Chat" className="flex min-w-0 flex-col gap-5">
          <FileDrop
            accept="image/png,image/jpeg,application/pdf"
            file={null}
            onFile={(f) => void onFile(f)}
            prompt={usable ? "Swap the file" : "Add your card or page"}
            hint={uploading ? "Reading the page…" : "PDF, JPG or PNG"}
            compact
            disabled={uploading}
            name="chat-file"
          />
          {shownNotice ? (
            <Notice
              tone={shownNotice.tone}
              title={shownNotice.tone === "refusal" ? "Not this one" : undefined}
              testId={shownNotice.tone === "refusal" ? "notice-refusal" : "notice-error"}
            >
              {shownNotice.text}
            </Notice>
          ) : null}
          <div className="max-h-[22rem] min-h-[8rem] overflow-y-auto rounded-surface border border-hairline bg-sheet p-4">
            <div role="log" aria-live="polite" aria-label="Messages">
              <MessageList messages={messages} thinking={sending} />
            </div>
          </div>
          <Composer onSend={onSend} busy={sending} />
        </section>
      </div>
    </main>
  );
}

