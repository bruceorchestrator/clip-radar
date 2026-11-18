import { EngineError, fetchVideo, isClipFileName, isJobId } from "@/lib/engine";

const PASS_THROUGH = ["content-type", "content-length", "content-range", "accept-ranges"];

export async function GET(
  request: Request,
  { params }: { params: Promise<{ job: string; file: string }> },
) {
  const { job, file } = await params;
  // "headline" and "stacked" hold the gateway-made versions of a clip (title instead of
  // captions; webcam on top with the game below).
  const gatewayMade = (job === "headline" || job === "stacked") && /^[0-9a-f]{32}-[0-9a-f]{8}\.mp4$/.test(file);
  if (!gatewayMade && (!isJobId(job) || !isClipFileName(file))) return new Response("Not found", { status: 404 });

  let upstream: Response;
  try {
    upstream = await fetchVideo(
      `/videos/${job}/${encodeURIComponent(file)}`,
      request.headers.get("range"),
    );
  } catch (error) {
    if (error instanceof EngineError) return new Response(error.message, { status: error.status });
    throw error;
  }
  if (!upstream.ok && upstream.status !== 206) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  for (const name of PASS_THROUGH) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (new URL(request.url).searchParams.has("download")) {
    headers.set("Content-Disposition", `attachment; filename="${file.replace(/"/g, "")}"`);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
