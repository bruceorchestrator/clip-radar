"use client";

import { useSyncExternalStore } from "react";

export const THEMES = [
  { key: "dark", label: "Dark" },
  { key: "dim", label: "Dim" },
  { key: "cream", label: "Cream" },
] as const;

export type Theme = (typeof THEMES)[number]["key"];

const STORAGE_KEY = "clip-radar-theme";

/** Runs before paint (inline in <head>) so the saved theme never flashes. */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${STORAGE_KEY}");if(t==="dim"||t==="cream"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

function current(): Theme {
  const t = document.documentElement.dataset.theme;
  return t === "dim" || t === "cream" ? t : "dark";
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the theme still applies for this visit.
  }
  listeners.forEach((l) => l());
}

export function ThemeSwitcher() {
  const theme = useSyncExternalStore(subscribe, current, () => "dark" as Theme);
  return (
    <div role="group" aria-label="Theme" className="flex gap-1 rounded-full border border-line bg-panel p-1">
      {THEMES.map((t) => (
        <button
          key={t.key}
          type="button"
          aria-pressed={theme === t.key}
          onClick={() => setTheme(t.key)}
          className={
            theme === t.key
              ? "rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-ink"
              : "rounded-full px-3 py-1 text-xs text-muted hover:text-fg"
          }
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
