import type { HandStatus } from "@/lib/api";

const LABELS: Record<HandStatus, string> = {
  empty: "No handwriting yet",
  learning: "Learning your hand",
  ready: "Ready to write",
  failed: "Needs another page",
};

const TONES: Record<HandStatus, string> = {
  empty: "bg-paper-well text-ink-mid border-hairline-strong",
  learning: "bg-wait-bg text-wait border-wait/30",
  ready: "bg-ok-bg text-ok border-ok/30",
  failed: "bg-crit-bg text-crit border-crit/30",
};

/** Status shown as shape + words (never colour alone): ● ring, ◐ half, ✓ tick, ! mark. */
function Glyph({ status }: { status: HandStatus }) {
  const common = { width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": true } as const;
  if (status === "ready")
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M2.5 7.5 5.5 10.5 11.5 3.5" />
      </svg>
    );
  if (status === "failed")
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M7 2.5v5M7 11v.01" />
      </svg>
    );
  if (status === "learning")
    return (
      <svg {...common} fill="currentColor" stroke="currentColor" strokeWidth="1.5">
        <circle cx="7" cy="7" r="5" fill="none" />
        <path d="M7 2a5 5 0 0 1 0 10z" />
      </svg>
    );
  return (
    <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="7" cy="7" r="5" strokeDasharray="2 2" />
    </svg>
  );
}

export function statusLabel(status: HandStatus): string {
  return LABELS[status];
}

export function StatusChip({ status }: { status: HandStatus }) {
  return (
    <span
      role="status"
      data-status={status}
      className={`inline-flex min-h-8 items-center gap-2 rounded-full border px-3 text-[0.875rem] font-semibold ${TONES[status]}`}
    >
      <Glyph status={status} />
      {LABELS[status]}
    </span>
  );
}
