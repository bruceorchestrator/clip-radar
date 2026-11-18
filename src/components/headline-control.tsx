"use client";

import { useState } from "react";

/** Captions came out wrong (music over speech)? Swap them for one big title. */
export function HeadlineControl({ hook, headline, editable, busy, onSet, onClear }: {
  hook: string;
  headline: string | null;
  editable: boolean;
  busy: boolean;
  onSet: (text: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  // Emoji do not render in the title font, so the suggestion leaves them out.
  const [text, setText] = useState(headline ?? hook.replace(/[^\p{L}\p{N}\s'’!?.,:&-]/gu, "").trim());

  if (!editable) return headline ? <p className="text-xs text-muted">Headline: &ldquo;{headline}&rdquo;</p> : null;

  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {headline ? <span className="text-muted">Headline instead of captions: &ldquo;{headline}&rdquo;</span> : null}
        <button type="button" disabled={busy} onClick={() => setOpen(true)} className="text-fg/85 underline hover:text-fg disabled:opacity-60">
          {headline ? "Change headline" : "Captions look wrong? Use a headline"}
        </button>
        {headline ? (
          <button type="button" disabled={busy} onClick={onClear} className="text-fg/85 underline hover:text-fg disabled:opacity-60">
            Back to captions
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-xl border border-line p-3">
      <label className="block space-y-1">
        <span className="text-xs text-muted">White title on black, no captions</span>
        <input
          value={text}
          maxLength={90}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy || !text.trim()}
          onClick={() => {
            onSet(text.trim());
            setOpen(false);
          }}
          className="rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink disabled:opacity-60"
        >
          {busy ? "Making it… about 30 s" : "Make headline"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-full border border-line px-3 py-1.5 text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}
