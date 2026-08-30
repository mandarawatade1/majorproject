import { API_BASE_URL } from "@/lib/api";

/**
 * Proxies the answer stream from FastAPI to the browser.
 *
 * The question could be posted to the API directly — CORS already allows
 * localhost:3000 — but proxying is better here for three reasons. The API host
 * stays server-side, so the portal works unchanged if FastAPI is ever on a
 * private network. Everything arrives from one origin, so there is no preflight
 * on the way to a long-lived stream. And the browser needs no build-time
 * knowledge of where the backend lives.
 *
 * The upstream body is handed straight through rather than read and re-emitted.
 * Buffering it here would collect the whole answer before sending anything,
 * which is precisely the behaviour SSE exists to avoid: under C5 a user would
 * stare at nothing for three hundred seconds and then get everything at once.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
  } catch {
    return sseError(`could not reach the API at ${API_BASE_URL}`);
  }

  // A failure before the stream opens still has a status code, so it arrives
  // as JSON rather than as events. Translating it into a single `error` event
  // means the client has one failure path instead of two.
  if (!upstream.ok || !upstream.body) {
    let detail = `the API answered ${upstream.status}`;
    try {
      const payload = (await upstream.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      /* keep the status-code message */
    }
    return sseError(detail);
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      // no-transform matters as much as no-cache: a compressing proxy would
      // buffer the stream to compress it.
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

function sseError(message: string): Response {
  const body = `event: error\ndata: ${JSON.stringify({ message })}\n\n`;
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}
