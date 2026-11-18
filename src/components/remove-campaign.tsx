"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RemoveCampaign({ id, name }: { id: string; name: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!window.confirm(`Remove "${name}"? Clips stop being checked against it.`)) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/campaigns/${encodeURIComponent(id)}/remove`, { method: "POST" });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { error?: string };
        setError(body.error ?? "Could not remove it.");
        return;
      }
      router.refresh();
    } catch {
      setError("Lost the connection. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      <button type="button" disabled={busy} onClick={remove} className="text-sm text-muted underline hover:text-bad disabled:opacity-60">
        Remove
      </button>
      {error ? <span className="text-xs text-bad">{error}</span> : null}
    </span>
  );
}
