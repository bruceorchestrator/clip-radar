"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { applyForm, FORM_PLATFORMS, formWarnings, toForm, type CampaignForm, type Draft } from "@/lib/campaign-form";

const input = "w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none";
const label = "text-xs uppercase tracking-wide text-muted";

function Field({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className={label}>{name}</span>
      {children}
    </label>
  );
}

/** Paste a brief link or text, review what we read, save it as a campaign. */
export function CampaignImport() {
  const router = useRouter();
  const [mode, setMode] = useState<"url" | "text">("url");
  const [source, setSource] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [form, setForm] = useState<CampaignForm | null>(null);
  const [busy, setBusy] = useState<"import" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function read() {
    setBusy("import");
    setError(null);
    try {
      const response = await fetch("/api/campaigns/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "url" ? { url: source } : { text: source }),
      });
      const body = (await response.json().catch(() => ({}))) as { campaign?: Draft; error?: string };
      if (!response.ok || !body.campaign) {
        setError(body.error ?? "Could not read this brief.");
        return;
      }
      setDraft(body.campaign);
      setForm(toForm(body.campaign));
    } catch {
      setError("Lost the connection. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!draft || !form) return;
    setBusy("save");
    setError(null);
    try {
      const response = await fetch("/api/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign: applyForm(draft, form) }),
      });
      const body = (await response.json().catch(() => ({}))) as { error?: string };
      if (!response.ok) {
        setError(body.error ?? "Could not save the campaign.");
        return;
      }
      setDraft(null);
      setForm(null);
      setSource("");
      router.refresh();
    } catch {
      setError("Lost the connection. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const set = (patch: Partial<CampaignForm>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const warnings = form ? formWarnings(form) : [];

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-medium">Add a campaign</h2>
        <div className="flex gap-2 text-sm">
          {(["url", "text"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={mode === m ? "rounded-full bg-accent px-3 py-1 font-medium text-accent-ink" : "rounded-full border border-line px-3 py-1 text-fg/85"}
            >
              {m === "url" ? "Link" : "Paste rules"}
            </button>
          ))}
        </div>
      </div>
      {mode === "url" ? (
        <input
          className={input}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="https://reachclipping.com/LACYGTA or a contentrewards.com campaign link"
        />
      ) : (
        <textarea
          className={`${input} min-h-40`}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="Paste the campaign rules from Discord, Whop or anywhere else"
        />
      )}
      <button
        type="button"
        disabled={!source.trim() || busy !== null}
        onClick={read}
        className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
      >
        {busy === "import" ? "Reading the rules… about 10 s" : "Read the rules"}
      </button>
      {error ? <p className="text-sm text-bad">{error}</p> : null}

      {form ? (
        <div className="space-y-4 border-t border-line pt-4">
          <p className="text-sm text-muted">Check what we read, fix anything that is off, then save.</p>
          {warnings.map((w) => (
            <p key={w} className="text-sm text-warn">{w}</p>
          ))}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field name="Campaign name"><input className={input} value={form.name} onChange={(e) => set({ name: e.target.value })} /></Field>
            <Field name="Streamer logins (Twitch / Kick)"><input className={input} value={form.channels} onChange={(e) => set({ channels: e.target.value })} placeholder="lacy, jasontheween" /></Field>
            <Field name="Footage from (date)"><input type="date" className={input} value={form.since} onChange={(e) => set({ since: e.target.value })} /></Field>
            <Field name="Name in caption or on screen"><input className={input} value={form.mustMention} onChange={(e) => set({ mustMention: e.target.value })} /></Field>
            <Field name="Required hashtags"><input className={input} value={form.hashtags} onChange={(e) => set({ hashtags: e.target.value })} /></Field>
            <Field name="Submit within (minutes)"><input inputMode="numeric" className={input} value={form.submitWithinMin} onChange={(e) => set({ submitWithinMin: e.target.value })} /></Field>
            <Field name="Views needed in total"><input inputMode="numeric" className={input} value={form.minTotalViews} onChange={(e) => set({ minTotalViews: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field name="Min length (s)"><input inputMode="numeric" className={input} value={form.minSec} onChange={(e) => set({ minSec: e.target.value })} /></Field>
              <Field name="Max length (s)"><input inputMode="numeric" className={input} value={form.maxSec} onChange={(e) => set({ maxSec: e.target.value })} /></Field>
            </div>
          </div>
          <fieldset className="space-y-2">
            <legend className={label}>Platforms</legend>
            <div className="flex flex-wrap gap-3 text-sm">
              {FORM_PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={form.platforms.includes(p)}
                    onChange={(e) => set({ platforms: e.target.checked ? [...form.platforms, p] : form.platforms.filter((x) => x !== p) })}
                  />
                  {p}
                </label>
              ))}
            </div>
          </fieldset>
          <Field name="Payout"><input className={input} value={form.payout} onChange={(e) => set({ payout: e.target.value })} /></Field>
          <Field name="Checked by eye (one rule per line)">
            <textarea className={`${input} min-h-48`} value={form.manual} onChange={(e) => set({ manual: e.target.value })} />
          </Field>
          <div className="flex gap-2">
            <button type="button" disabled={busy !== null || !form.name.trim()} onClick={save} className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60">
              {busy === "save" ? "Saving…" : "Save campaign"}
            </button>
            <button type="button" onClick={() => { setDraft(null); setForm(null); }} className="rounded-full border border-line px-4 py-2 text-sm hover:border-muted">
              Discard
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
