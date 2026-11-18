import { Suspense } from "react";
import { ClipForm } from "@/components/clip-form";
import { isSupportedSourceUrl } from "@/lib/clip-source";
import { previewVideo } from "@/lib/engine";
import type { Preview } from "@/lib/launch";

type RawParams = { [key: string]: string | string[] | undefined };

function first(value: string | string[] | undefined): string {
  return typeof value === "string" ? value : "";
}

async function Prefilled({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const url = first(params.url);
  let preview: Preview | null = null;
  if (isSupportedSourceUrl(url)) {
    // A link from the radar: show the stream at once. A failure just leaves the form to retry.
    preview = await previewVideo(url).catch(() => null);
  }
  return (
    <ClipForm
      defaultUrl={url}
      defaultStart={first(params.start)}
      defaultEnd={first(params.end)}
      initialPreview={preview}
    />
  );
}

export default function ClipPage({ searchParams }: { searchParams: Promise<RawParams> }) {
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight">Make clips</h1>
      <p className="mt-2 text-muted">
        Paste a stream or video link. See where the hot moments are, pick how many clips you want, and get vertical clips with captions and a hook.
      </p>
      <div className="mt-8">
        <Suspense fallback={<p className="text-muted">Loading…</p>}>
          <Prefilled searchParams={searchParams} />
        </Suspense>
      </div>
    </main>
  );
}
