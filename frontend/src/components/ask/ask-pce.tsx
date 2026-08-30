"use client";

import { useCallback, useRef, useState } from "react";

import { DemoBadge } from "@/components/demo-badge";
import { displaySource } from "@/lib/citation";
import {
  readEventStream,
  type AnswerPayload,
  type SourceRef,
  type StageEvent,
} from "@/lib/sse";

const CONFIGS = [
  { name: "C3", label: "Standard", hint: "Hybrid retrieval with cross-encoder reranking" },
  { name: "C5", label: "Verified", hint: "Adds iterative retrieval and answer verification" },
];

const EXAMPLES = [
  "What is the intake for Computer Engineering?",
  "Which accreditations does the college hold?",
  "What programmes does the Mechanical Engineering department run?",
];

type Status = "idle" | "streaming" | "done" | "error";

export function AskPce() {
  const [question, setQuestion] = useState("");
  const [config, setConfig] = useState("C3");
  const [status, setStatus] = useState<Status>("idle");
  const [stages, setStages] = useState<StageEvent[]>([]);
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [preview, setPreview] = useState("");
  const [answer, setAnswer] = useState<AnswerPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const ask = useCallback(
    async (asked: string) => {
      const text = asked.trim();
      if (text.length < 3 || status === "streaming") return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStatus("streaming");
      setStages([]);
      setSources([]);
      setPreview("");
      setAnswer(null);
      setError(null);

      try {
        const response = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: text, config }),
          signal: controller.signal,
        });

        if (!response.body) {
          setError("the answer stream did not open");
          setStatus("error");
          return;
        }

        for await (const event of readEventStream(response.body, controller.signal)) {
          if (event.name === "stage") {
            setStages((current) => [...current, event.data]);
          } else if (event.name === "sources") {
            setSources(event.data.sources);
          } else if (event.name === "token") {
            setPreview((current) => current + event.data.text);
          } else if (event.name === "answer") {
            // The authoritative text. It replaces the preview rather than
            // confirming it — under C5 this is where an unsupported answer is
            // withdrawn, and rendering the accumulated tokens instead would
            // show the user the claim the system just decided not to make.
            setAnswer(event.data);
          } else if (event.name === "done") {
            setStatus("done");
          } else if (event.name === "error") {
            setError(event.data.message);
            setStatus("error");
          }
        }
        // A stream that ends without `done` ended badly — most often the API
        // process died mid-answer. Saying so beats leaving a spinner running.
        setStatus((current) => (current === "streaming" ? "error" : current));
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : "the request failed");
        setStatus("error");
      }
    },
    [config, status],
  );

  const streaming = status === "streaming";

  return (
    <div className="container-page grid gap-10 py-10 lg:grid-cols-[minmax(0,1fr)_330px]">
      <div className="min-w-0">
        <form
          onSubmit={(submitEvent) => {
            submitEvent.preventDefault();
            void ask(question);
          }}
        >
          <label htmlFor="question" className="eyebrow mb-2 block">
            Your question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(changeEvent) => setQuestion(changeEvent.target.value)}
            onKeyDown={(keyEvent) => {
              if (keyEvent.key === "Enter" && (keyEvent.metaKey || keyEvent.ctrlKey)) {
                keyEvent.preventDefault();
                void ask(question);
              }
            }}
            rows={3}
            maxLength={500}
            placeholder="Ask about departments, programmes, admissions, accreditation…"
            className="w-full resize-y rounded-lg border border-line bg-white px-4 py-3 text-[15px] leading-relaxed text-ink placeholder:text-ink-muted"
          />

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <fieldset className="flex items-center gap-2">
              <legend className="sr-only">Pipeline configuration</legend>
              {CONFIGS.map((option) => (
                <label
                  key={option.name}
                  title={option.hint}
                  className={`cursor-pointer rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${
                    config === option.name
                      ? "border-navy-900 bg-navy-900 text-white"
                      : "border-line bg-white text-ink-soft hover:border-navy-200"
                  }`}
                >
                  <input
                    type="radio"
                    name="config"
                    value={option.name}
                    checked={config === option.name}
                    onChange={() => setConfig(option.name)}
                    className="sr-only"
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>

            <button
              type="submit"
              disabled={streaming || question.trim().length < 3}
              className="rounded-md bg-navy-900 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {streaming ? "Answering…" : "Ask"}
            </button>
          </div>
        </form>

        {status === "idle" ? (
          <div className="mt-8">
            <p className="eyebrow mb-3">Try one of these</p>
            <ul className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(example);
                      void ask(example);
                    }}
                    className="rounded-full border border-line bg-white px-4 py-1.5 text-left text-sm text-ink-soft transition-colors hover:border-navy-200 hover:text-ink"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {error ? (
          <div className="mt-8 card border-gold/30 bg-gold-soft/40 p-5">
            <p className="font-semibold text-ink">The answer could not be completed.</p>
            <p className="mt-1 text-sm text-ink-soft">{error}</p>
          </div>
        ) : null}

        {answer ? <AnswerView answer={answer} sources={sources} /> : null}

        {/* The preview, shown only while nothing authoritative has arrived. */}
        {!answer && preview ? (
          <section className="mt-8">
            <p className="eyebrow mb-2">Drafting…</p>
            <p className="whitespace-pre-wrap text-[16px] leading-relaxed text-ink-soft">
              {preview}
              <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-ink-muted align-middle" />
            </p>
          </section>
        ) : null}
      </div>

      <aside className="min-w-0 space-y-8">
        <StageTimeline stages={stages} streaming={streaming} />
        <SourceList sources={sources} />
      </aside>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function AnswerView({ answer, sources }: { answer: AnswerPayload; sources: SourceRef[] }) {
  const verification = answer.verification;

  return (
    <section className="mt-8">
      <div className="card p-6">
        <p className="whitespace-pre-wrap text-[17px] leading-relaxed text-ink">
          <Cited text={answer.answer} sources={sources} />
        </p>

        {answer.used_demo_sources ? (
          <p className="mt-5 flex items-center gap-2 text-sm text-ink-soft">
            <DemoBadge />
            This answer draws on synthetic records.
          </p>
        ) : null}

        <dl className="mt-5 flex flex-wrap gap-x-6 gap-y-1 border-t border-line pt-4 text-xs text-ink-muted">
          <div>
            <dt className="inline">Configuration </dt>
            <dd className="inline font-medium">{answer.config}</dd>
          </div>
          <div>
            <dt className="inline">Model </dt>
            <dd className="inline font-medium">{answer.model}</dd>
          </div>
          <div>
            <dt className="inline">Retrieval </dt>
            <dd className="inline font-medium">{(answer.retrieval_ms / 1000).toFixed(1)}s</dd>
          </div>
          <div>
            <dt className="inline">Generation </dt>
            <dd className="inline font-medium">{(answer.generation_ms / 1000).toFixed(1)}s</dd>
          </div>
        </dl>
      </div>

      {verification ? <VerificationPanel verification={verification} /> : null}
    </section>
  );
}

function VerificationPanel({ verification }: { verification: NonNullable<AnswerPayload["verification"]> }) {
  const refused = verification.refused;

  return (
    <div
      className={`card mt-4 p-5 ${refused ? "border-gold/40 bg-gold-soft/50" : "border-line"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-semibold text-ink">
          {refused ? "This answer was withheld" : `Verification: ${verification.verdict}`}
        </p>
        {verification.support_rate !== null ? (
          <span className="text-sm text-ink-muted">
            {Math.round(verification.support_rate * 100)}% of claims supported
          </span>
        ) : null}
      </div>

      {verification.unsupported_sentences.length > 0 ? (
        <div className="mt-3">
          <p className="eyebrow mb-2">Not supported by the retrieved sources</p>
          <ul className="space-y-1.5 text-sm text-ink-soft">
            {verification.unsupported_sentences.map((sentence) => (
              <li key={sentence} className="border-l-2 border-gold/50 pl-3">
                {sentence}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* What was withheld, shown behind a disclosure rather than discarded.
          A refusal nobody can inspect is a refusal nobody can check. */}
      {verification.withheld_text ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-navy-700">
            Show the text that was withheld
          </summary>
          <p className="mt-2 whitespace-pre-wrap border-l-2 border-line pl-3 text-sm leading-relaxed text-ink-muted">
            {verification.withheld_text}
          </p>
        </details>
      ) : null}
    </div>
  );
}

/**
 * Renders `[S1]` markers as links to the source panel.
 *
 * This is the phase's stated bar — a stranger tracing a sentence back to a page
 * number — so the citation has to be a control, not decoration.
 */
function Cited({ text, sources }: { text: string; sources: SourceRef[] }) {
  const known = new Set(sources.map((source) => source.marker));
  const parts = text.split(/(\[S\d+\])/g);

  return (
    <>
      {parts.map((part, index) =>
        /^\[S\d+\]$/.test(part) && known.has(part) ? (
          <a
            key={`${part}-${index}`}
            href={`#source-${part.slice(2, -1)}`}
            className="mx-0.5 rounded bg-navy-100 px-1.5 py-0.5 align-baseline text-[13px] font-semibold text-navy-700 no-underline hover:bg-navy-200"
          >
            {part}
          </a>
        ) : (
          <span key={`text-${index}`}>{part}</span>
        ),
      )}
    </>
  );
}

function StageTimeline({ stages, streaming }: { stages: StageEvent[]; streaming: boolean }) {
  if (stages.length === 0 && !streaming) return null;

  return (
    <section>
      <h2 className="eyebrow mb-3">What the system is doing</h2>
      <ol className="space-y-2 text-sm">
        {stages.map((stage, index) => (
          <li key={index} className="flex gap-2 text-ink-soft">
            <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-navy-200" />
            <span>{describe(stage)}</span>
          </li>
        ))}
        {streaming ? (
          <li className="flex gap-2 text-ink-muted">
            <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-gold" />
            <span>working…</span>
          </li>
        ) : null}
      </ol>
    </section>
  );
}

/** Plain English for each stage event. The agent's rounds are the interesting
 *  part: they are the only place a user can watch the system decide something. */
function describe(stage: StageEvent): string {
  if (stage.stage === "retrieval" && stage.status === "started") {
    return `Searching the knowledge base (${stage.config ?? ""})`.trim();
  }
  if (stage.stage === "retrieval" && stage.status === "finished") {
    const reranked = stage.reranked_to ? `, reranked to ${stage.reranked_to}` : "";
    const seconds = stage.elapsed_ms ? ` in ${(stage.elapsed_ms / 1000).toFixed(1)}s` : "";
    return `Found ${stage.passages ?? 0} passages${reranked}${seconds}`;
  }
  if (stage.stage === "agent" && stage.status === "finished") {
    return `Stopped searching: ${stage.stop_reason ?? "done"}`;
  }
  if (stage.stage === "agent") {
    const round = stage.iteration ? `Round ${stage.iteration}` : "Searching again";
    const query = stage.query ? ` — “${stage.query}”` : "";
    const found = typeof stage.new_passages === "number" ? `, ${stage.new_passages} new passages` : "";
    return `${round}${query}${found}`;
  }
  if (stage.stage === "generation") return "Writing the answer";
  if (stage.stage === "verification" && stage.status === "finished") {
    return `Checked ${stage.checked ?? 0} claims — ${stage.unsupported ?? 0} unsupported`;
  }
  if (stage.stage === "verification") return "Checking the answer against the sources";
  return stage.stage;
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  if (sources.length === 0) return null;

  return (
    <section>
      <h2 className="eyebrow mb-3">Sources</h2>
      <ol className="space-y-3">
        {sources.map((source) => {
          const display = displaySource(source);
          return (
          <li
            key={source.chunk_id}
            id={`source-${source.marker.slice(2, -1)}`}
            className="card p-4 target:border-gold"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="rounded bg-navy-100 px-1.5 py-0.5 text-[12px] font-semibold text-navy-700">
                {source.marker}
              </span>
              {source.is_demo ? <DemoBadge /> : null}
            </div>
            {/* The label the pipeline recorded is kept on hover, so the tidied
                display never becomes the only version a reader can see. */}
            <p className="mt-2 text-sm font-medium leading-snug text-ink" title={display.raw}>
              {display.title}
            </p>
            {display.section ? (
              <p className="mt-1 text-xs leading-snug text-ink-soft">{display.section}</p>
            ) : null}
            {source.page !== null ? (
              <p className="mt-1 text-xs text-ink-muted">Page {source.page}</p>
            ) : null}
            {source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-2 inline-block break-all text-xs text-navy-700 link-underline"
              >
                {source.url}
              </a>
            ) : null}
          </li>
          );
        })}
      </ol>
    </section>
  );
}
