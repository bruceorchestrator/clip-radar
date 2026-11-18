import { NextResponse } from "next/server";
import { EngineError, getBatch, isBatchId } from "@/lib/engine";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isBatchId(id)) return NextResponse.json({ error: "Job not found." }, { status: 404 });
  try {
    const batch = await getBatch(id);
    if (!batch) return NextResponse.json({ error: "Job not found." }, { status: 404 });
    return NextResponse.json(batch, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof EngineError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    throw error;
  }
}
