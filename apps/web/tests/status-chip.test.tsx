import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatusChip, statusLabel } from "../src/components/status-chip";
import type { HandStatus } from "../src/lib/api";

describe("StatusChip", () => {
  const cases: [HandStatus, string][] = [
    ["empty", "No handwriting yet"],
    ["learning", "Learning your hand"],
    ["ready", "Ready to write"],
    ["failed", "Needs another page"],
  ];

  it.each(cases)("%s shows the words %s, not just a colour", (status, label) => {
    const html = renderToStaticMarkup(<StatusChip status={status} />);
    expect(html).toContain(label);
    expect(html).toContain(`data-status="${status}"`);
    expect(html).toContain('role="status"');
    expect(statusLabel(status)).toBe(label);
  });
});
