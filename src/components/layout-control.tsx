/** Webcam on top with the game below, or the engine's own framing for this clip. */
export function LayoutControl({ layout, error, editable, busy, onSwitch }: {
  layout: "stacked" | "engine" | null;
  error: string | null;
  editable: boolean;
  busy: boolean;
  onSwitch: (to: "stacked" | "engine") => void;
}) {
  if (!layout) return null;
  const stacked = layout === "stacked";
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="text-muted">{stacked ? "Webcam on top, game below" : "Engine framing"}</span>
      {editable ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onSwitch(stacked ? "engine" : "stacked")}
          className="text-fg/85 underline hover:text-fg disabled:opacity-60"
        >
          {busy ? "Re-cutting… about a minute" : stacked ? "Use the engine framing" : "Put the webcam on top"}
        </button>
      ) : null}
      {!stacked && error ? <span className="w-full text-warn">Webcam-on-top failed: {error}</span> : null}
    </div>
  );
}
