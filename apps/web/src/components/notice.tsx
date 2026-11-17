import type { ReactNode } from "react";

type Tone = "refusal" | "error" | "info";

const TONES: Record<Tone, string> = {
  refusal: "bg-notice text-notice-ink border-margin/40",
  error: "bg-crit-bg text-crit border-crit/30",
  info: "bg-paper-well text-ink-mid border-hairline-strong",
};

/** Inline notice. Refusals read as a friendly note in the margin (red rule), not as an alarm. */
export function Notice({
  tone,
  title,
  children,
  testId,
}: {
  tone: Tone;
  title?: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      data-testid={testId ?? `notice-${tone}`}
      className={`rise rounded-control border border-l-4 px-4 py-3 text-[0.9375rem] ${TONES[tone]} ${
        tone === "refusal" ? "border-l-margin" : ""
      }`}
    >
      {title ? <p className="hand text-[1.6rem]">{title}</p> : null}
      <p>{children}</p>
    </div>
  );
}
