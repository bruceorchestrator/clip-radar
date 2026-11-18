import { Suspense } from "react";
import { ClipForm } from "@/components/clip-form";
import { ReadyClipForm } from "@/components/ready-clip-form";
import { isSupportedSourceUrl } from "@/lib/clip-source";
import { getAutopilot, previewVideo } from "@/lib/engine";
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

async function ReadyClip() {
  const streamers = await getAutopilot()
    .then((a) => a.streamers.map((s) => ({ login: s.login, name: s.name })))
    .catch(() => []);
  return <ReadyClipForm streamers={streamers} />;
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

      <section className="mt-14 border-t border-line pt-10">
        <h2 className="text-2xl font-semibold tracking-tight">Already have the clip?</h2>
        <p className="mt-2 text-muted">
          A moment you picked yourself, from a clip library or a Kick or Twitch clip. It gets captions, a hook and the
          webcam-on-top layout, then waits on Autopilot for your post.
        </p>
        <div className="mt-6">
          <Suspense fallback={<p className="text-muted">Loading…</p>}>
            <ReadyClip />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
