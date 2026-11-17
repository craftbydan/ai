"use client";

import { useId, useRef, useState } from "react";

/** Keyboard-usable drop zone: a real file input inside a label, so Tab + Enter/Space opens the
    picker and dragging a file onto it works too. */
export function FileDrop({
  accept,
  file,
  onFile,
  prompt,
  hint,
  compact = false,
  disabled = false,
  name = "file",
}: {
  accept: string;
  file: File | null;
  onFile: (file: File | null) => void;
  prompt: string;
  hint: string;
  compact?: boolean;
  disabled?: boolean;
  name?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <label
      htmlFor={id}
      data-over={over ? "true" : undefined}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const dropped = e.dataTransfer.files.item(0);
        if (dropped && !disabled) onFile(dropped);
      }}
      className={`block cursor-pointer rounded-surface border-2 border-dashed text-center transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-pen ${
        over ? "border-pen bg-pen-quiet" : "border-hairline-strong bg-paper-well hover:border-pen"
      } ${compact ? "px-4 py-5" : "px-6 py-10"} ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <input
        ref={input}
        id={id}
        name={name}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => {
          onFile(e.target.files?.item(0) ?? null);
          // Selecting the same file twice must still fire a change event.
          if (file === null) e.target.value = "";
        }}
      />
      <span className={`hand block text-ink ${compact ? "text-[1.6rem]" : "text-[2.1rem]"}`}>
        {file ? file.name : prompt}
      </span>
      <span className="mt-1 block text-[0.875rem] text-ink-mid">
        {file ? "Ready to upload. Choose another file to swap it." : hint}
      </span>
    </label>
  );
}
