import { NextResponse } from "next/server";
import { isSupportedSourceUrl } from "@/lib/clip-source";
import { EngineError, previewVideo } from "@/lib/engine";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { url?: unknown } | null;
  const url = typeof body?.url === "string" ? body.url.trim() : "";
  if (!isSupportedSourceUrl(url)) {
    return NextResponse.json({ error: "Paste a Twitch, Kick or YouTube link." }, { status: 400 });
  }
  try {
    return NextResponse.json(await previewVideo(url));
  } catch (error) {
    if (error instanceof EngineError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    throw error;
  }
}
