/**
 * Types and a parser for the answer stream.
 *
 * The event contract is defined by `rag/streaming.py` and documented on
 * `answer_events`. One rule governs everything here and is worth restating,
 * because a client that gets it wrong silently undoes C5:
 *
 *   **The `answer` event is authoritative; `token` events are a preview.**
 *
 * Verification runs *after* generation, so by the time it withholds an
 * unsupported answer the user has already watched that text arrive token by
 * token. The final `answer` event carries the text the system stands behind —
 * which may be a refusal replacing everything shown so far. Rendering the
 * accumulated tokens as the answer would display exactly the claim the system
 * decided not to make.
 */

export interface SourceRef {
  marker: string;
  label: string;
  url: string | null;
  page: number | null;
  is_demo: boolean;
  chunk_id: string;
}

export interface StageEvent {
  stage: "retrieval" | "agent" | "generation" | "verification" | string;
  status?: "started" | "finished" | string;
  config?: string;
  passages?: number;
  reranked_to?: number | null;
  elapsed_ms?: number;
  iteration?: number;
  query?: string;
  new_passages?: number;
  decision?: string;
  stop_reason?: string;
  verdict?: string;
  checked?: number;
  unsupported?: number;
  support_rate?: number;
  refused?: boolean;
}

export interface Verification {
  verdict: string;
  support_rate: number | null;
  unsupported_sentences: string[];
  refused: boolean;
  withheld_text: string | null;
}

export interface AnswerPayload {
  answer: string;
  config: string;
  model: string;
  used_demo_sources: boolean;
  latency_ms: number;
  retrieval_ms: number;
  generation_ms: number;
  verification?: Verification;
}

export type StreamEvent =
  | { name: "stage"; data: StageEvent }
  | { name: "sources"; data: { sources: SourceRef[]; contains_demo: boolean } }
  | { name: "token"; data: { text: string } }
  | { name: "answer"; data: AnswerPayload }
  | { name: "done"; data: { latency_ms: number } }
  | { name: "error"; data: { message: string } };

/**
 * Turn a byte stream of Server-Sent Events into parsed events.
 *
 * Written by hand rather than using `EventSource`, which only issues GET
 * requests — the question goes in a POST body. The buffering matters: a chunk
 * boundary can fall anywhere, including the middle of a JSON payload, so
 * events are only emitted once a complete `\n\n`-terminated block has arrived.
 */
export async function* readEventStream(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        const block = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const event = parseBlock(block);
        if (event) yield event;
        split = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseBlock(block: string): StreamEvent | null {
  let name = "message";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }

  if (dataLines.length === 0) return null;
  try {
    return { name, data: JSON.parse(dataLines.join("\n")) } as StreamEvent;
  } catch {
    // A malformed payload is dropped rather than thrown: one bad event must
    // not abort a stream whose remaining events are fine.
    return null;
  }
}
