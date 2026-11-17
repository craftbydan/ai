"use client";

import { useEffect, useState } from "react";
import { getAnalysis } from "@/lib/api";
import type { AnalysisRegion, PageAnalysis } from "@/lib/api";

const ZOOMS = [100, 150, 200] as const;
const KIND_LABEL: Record<AnalysisRegion["kind"], string> = {
  line: "Ruled line",
  box: "Box",
  blank: "Open space",
};

export function PagePreview({
  chatId,
  fileId,
  imageUrl,
  alt,
  pageCount,
  page,
  onPage,
  isRender,
}: {
  chatId: string;
  fileId: string;
  imageUrl: string;
  alt: string;
  pageCount: number;
  page: number;
  onPage: (p: number) => void;
  isRender: boolean;
}) {
  const [zoom, setZoom] = useState<(typeof ZOOMS)[number]>(100);
  const [showRegions, setShowRegions] = useState(false);
  const [pages, setPages] = useState<PageAnalysis[] | null>(null);
  const [regionError, setRegionError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    if (!showRegions || pages) return;
    let alive = true;
    getAnalysis(chatId, fileId)
      .then((a) => alive && setPages(a.pages))
      .catch(() => alive && setRegionError("Could not load the writable areas for this file."));
    return () => {
      alive = false;
    };
  }, [showRegions, pages, chatId, fileId]);

  const analysis = pages?.[page - 1];

  return (
    <section aria-label="Page preview" className="min-w-0">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Zoom" className="flex gap-1">
          {ZOOMS.map((z) => (
            <button
              key={z}
              type="button"
              className="btn btn-quiet !min-h-[44px] !px-3"
              aria-pressed={zoom === z}
              onClick={() => setZoom(z)}
            >
              {z}%
            </button>
          ))}
        </div>
        <button
          type="button"
          className="btn btn-quiet"
          aria-pressed={showRegions}
          onClick={() => setShowRegions((v) => !v)}
        >
          {showRegions ? "Hide writable areas" : "Show writable areas"}
        </button>
        {pageCount > 1 ? (
          <div role="group" aria-label="Page" className="ml-auto flex items-center gap-1">
            <button
              type="button"
              className="btn btn-quiet !px-3"
              disabled={page <= 1}
              onClick={() => onPage(page - 1)}
              aria-label="Previous page"
            >
              &lsaquo;
            </button>
            <span className="min-w-16 text-center text-[0.875rem] text-ink-mid">
              Page {page} of {pageCount}
            </span>
            <button
              type="button"
              className="btn btn-quiet !px-3"
              disabled={page >= pageCount}
              onClick={() => onPage(page + 1)}
              aria-label="Next page"
            >
              &rsaquo;
            </button>
          </div>
        ) : null}
      </div>
      {regionError ? <p className="mb-2 text-[0.875rem] text-crit">{regionError}</p> : null}

      <div
        className="max-h-[72vh] overflow-auto rounded-surface border border-hairline bg-paper-well p-3 sm:p-5"
        tabIndex={0}
        aria-label="Scrollable page"
      >
        <div
          className="relative mx-auto shadow-lift-3"
          style={{ width: `${zoom}%`, maxWidth: "none" }}
        >
          <PreviewImage
            key={imageUrl}
            src={imageUrl}
            alt={alt}
            testId={isRender ? "preview-image" : "page-image"}
          />
          {showRegions && analysis ? (
            <div className="absolute inset-0" data-testid="region-overlay">
              {analysis.regions.map((r) => {
                const [x0, y0, x1, y1] = r.bbox_px;
                const on = hovered === r.id;
                return (
                  <button
                    key={r.id}
                    type="button"
                    tabIndex={-1}
                    aria-label={`${KIND_LABEL[r.kind]}${r.signature ? ", signature area, not writable" : ""}`}
                    onMouseEnter={() => setHovered(r.id)}
                    onMouseLeave={() => setHovered(null)}
                    className={`absolute border-2 transition-colors ${
                      r.signature
                        ? "border-margin bg-margin/15"
                        : r.kind === "blank"
                          ? "border-pen bg-pen/10"
                          : "border-pen/60 bg-pen/5"
                    } ${on ? "!bg-pen/25" : ""}`}
                    style={{
                      left: `${(x0 / analysis.width) * 100}%`,
                      top: `${(y0 / analysis.height) * 100}%`,
                      width: `${((x1 - x0) / analysis.width) * 100}%`,
                      height: `${((y1 - y0) / analysis.height) * 100}%`,
                    }}
                  >
                    {on ? (
                      <span className="absolute -top-7 left-0 z-10 whitespace-nowrap rounded-inline bg-ink px-2 py-0.5 text-[0.75rem] font-semibold text-paper">
                        {r.signature ? "Signature area: stays blank" : KIND_LABEL[r.kind]}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
      <p className="mt-2 text-[0.8125rem] text-ink-low">
        {isRender
          ? "Preview of the latest version."
          : "Your file, before anything is written."}{" "}
        {showRegions
          ? "Blue areas are where I can write; red areas are signature spots and stay blank."
          : null}
      </p>
    </section>
  );
}

/** The image with a skeleton underneath until it has loaded; keyed by URL so it resets. */
function PreviewImage({ src, alt, testId }: { src: string; alt: string; testId: string }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <>
      {!loaded ? <div className="skeleton absolute inset-0 aspect-[3/4]" aria-hidden="true" /> : null}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        data-testid={testId}
        onLoad={() => setLoaded(true)}
        className="block h-auto w-full bg-sheet"
      />
    </>
  );
}
