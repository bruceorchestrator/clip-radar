import { NextResponse } from "next/server";
import { isSupportedSourceUrl } from "@/lib/clip-source";
import { EngineError, startReadyClip, uploadReadyClip } from "@/lib/engine";

const MAX_BYTES = 500 * 1024 * 1024;

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

/**
 * A ready clip into the review queue: form data with `streamer`, optional `name`
 * and `hook`, and either `file` (the video) or `url` (a clip link).
 */
export async function POST(request: Request) {
  const form = await request.formData().catch(() => null);
  if (!form) return NextResponse.json({ error: "Send the form." }, { status: 400 });
  if (field(form, "rightsConfirmed") !== "true") {
    return NextResponse.json({ error: "Confirm that you have the right to post this clip." }, { status: 400 });
  }
  const streamer = field(form, "streamer");
  if (!streamer) return NextResponse.json({ error: "Name the streamer in the clip." }, { status: 400 });
  const clip = { streamer, name: field(form, "name") || undefined, hook: field(form, "hook") || undefined };
  const file = form.get("file");
  const url = field(form, "url");
  try {
    if (file instanceof Blob && file.size > 0) {
      if (file.size > MAX_BYTES) return NextResponse.json({ error: "The file is over 500 MB." }, { status: 400 });
      return NextResponse.json(await uploadReadyClip(file, clip), { status: 201 });
    }
    if (!isSupportedSourceUrl(url)) {
      return NextResponse.json({ error: "Upload the video or paste a Twitch, Kick or YouTube clip link." }, { status: 400 });
    }
    return NextResponse.json(await startReadyClip(url, clip), { status: 201 });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
