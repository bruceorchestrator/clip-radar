import { NextResponse } from "next/server";
import { importBrief } from "@/lib/campaign-engine";
import { EngineError } from "@/lib/engine";

const MAX_TEXT = 20_000;

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { url?: unknown; text?: unknown } | null;
  const url = typeof body?.url === "string" ? body.url.trim() : "";
  const text = typeof body?.text === "string" ? body.text.trim() : "";
  if (!url && !text) return NextResponse.json({ error: "Paste a campaign link or the rules text." }, { status: 400 });
  if (url && !/^https:\/\/(www\.)?(reachclipping|contentrewards)\.com\//.test(url)) {
    return NextResponse.json({ error: "Paste a reachclipping.com or contentrewards.com link, or paste the rules as text." }, { status: 400 });
  }
  if (text.length > MAX_TEXT) return NextResponse.json({ error: "That text is too long. Paste only the rules." }, { status: 400 });
  try {
    const reply = await importBrief(url ? { url } : { text });
    return NextResponse.json(reply.body, { status: reply.status });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
