import { NextResponse } from "next/server";
import { isSupportedSourceUrl } from "@/lib/clip-source";
import { EngineError, startBatch } from "@/lib/engine";
import { CLIP_COUNTS, CLIP_FORMATS, CLIP_LENGTHS, type ClipCount, type ClipFormat, type ClipLength, type Mode } from "@/lib/launch";
import type { ClipSource } from "@/lib/types";

const MIN_STRETCH_SEC = 45;
const MAX_STRETCH_SEC = 600;

function seconds(value: unknown): number | undefined | null {
  if (value === undefined || value === null || value === "") return undefined;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return NextResponse.json({ error: "Send a JSON body." }, { status: 400 });

  if (body.rightsConfirmed !== true) {
    return NextResponse.json(
      { error: "Confirm that you have the right to clip this content." },
      { status: 400 },
    );
  }
  const url = typeof body.url === "string" ? body.url.trim() : "";
  if (!isSupportedSourceUrl(url)) {
    return NextResponse.json(
      { error: "Paste a Twitch, Kick or YouTube link." },
      { status: 400 },
    );
  }
  const start = seconds(body.sourceStart);
  const end = seconds(body.sourceEnd);
  if (start === null || end === null) {
    return NextResponse.json({ error: "Start and end must be seconds." }, { status: 400 });
  }
  if ((start === undefined) !== (end === undefined)) {
    return NextResponse.json({ error: "Fill in both start and end, or leave both empty." }, { status: 400 });
  }
  if (start !== undefined && end !== undefined && (end - start < MIN_STRETCH_SEC || end - start > MAX_STRETCH_SEC)) {
    return NextResponse.json(
      { error: "The stretch must be between 45 seconds and 10 minutes." },
      { status: 400 },
    );
  }

  const mode: Mode = start !== undefined ? "stretch" : body.mode === "whole" ? "whole" : "auto";
  const clips = Number(body.clips ?? 10) as ClipCount;
  if (!CLIP_COUNTS.includes(clips)) {
    return NextResponse.json({ error: "Pick 5, 10 or 20 clips." }, { status: 400 });
  }
  const length = String(body.length ?? "medium") as ClipLength;
  if (!(length in CLIP_LENGTHS)) {
    return NextResponse.json({ error: "Pick a clip length." }, { status: 400 });
  }
  const format = String(body.format ?? "vertical") as ClipFormat;
  if (!(format in CLIP_FORMATS)) {
    return NextResponse.json({ error: "Pick a format." }, { status: 400 });
  }

  const source: ClipSource = { url, sourceStart: start, sourceEnd: end };
  try {
    return NextResponse.json({ id: await startBatch(source, { mode, clips, length, format }) }, { status: 201 });
  } catch (error) {
    if (error instanceof EngineError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    throw error;
  }
}
