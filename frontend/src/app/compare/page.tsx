import Link from "next/link";
import type { Metadata } from "next";

import { ApiError, EmptyState } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { displaySource } from "@/lib/citation";
import { firstParam, type SearchParams } from "@/lib/types";

export const metadata: Metadata = { title: "Baseline vs proposed" };

type Props = { searchParams: SearchParams };

/**
 * The ablation, shown rather than asserted.
 *
 * Rendered from the recorded evaluation runs, not from live answers. The same
 * question asked three times through this system produced three different
 * citations, so a page that ran each configuration once and put the results
 * side by side would be presenting a coin flip as a measurement. These are the
 * runs Chapter 4 reports.
 */
export default async function ComparePage({ searchParams }: Props) {
  const index = await api.compareIndex();

  if (!index.ok) {
    return (
      <>
        <Header />
        <div className="container-page py-12">
          <ApiError message={index.error} />
        </div>
      </>
    );
  }

  const { questions, configs } = index.data;
  if (questions.length === 0) {
    return (
      <>
        <Header />
        <div className="container-page py-12">
          <EmptyState
            title="No evaluation runs are available."
            detail={index.data.note ?? "The eval/ directory is not mounted into the API container."}
          />
        </div>
      </>
    );
  }

  const questionId = firstParam(searchParams.q) ?? questions[0].id;
  const baseline = firstParam(searchParams.baseline) ?? "C0";
  const proposed = firstParam(searchParams.proposed) ?? "C3";

  const comparison = await api.compareQuestion(questionId, [baseline, proposed]);

  return (
    <>
      <Header />

      <div className="container-page py-10">
        <nav aria-label="Evaluated questions" className="mb-8">
          <p className="eyebrow mb-3">The twenty evaluated questions</p>
          <ul className="flex flex-wrap gap-2">
            {questions.map((question, position) => {
              const active = question.id === questionId;
              return (
                <li key={question.id}>
                  <Link
                    href={`/compare?q=${question.id}&baseline=${baseline}&proposed=${proposed}`}
                    aria-current={active ? "true" : undefined}
                    title={question.question}
                    className={`inline-block rounded border px-2.5 py-1 text-xs font-medium transition-colors ${
                      active
                        ? "border-navy-900 bg-navy-900 text-white"
                        : "border-line bg-white text-ink-soft hover:border-navy-200"
                    }`}
                  >
                    {position + 1}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {!comparison.ok ? (
          <ApiError message={comparison.error} />
        ) : (
          <>
            <p className="mb-8 max-w-prose font-serif text-xl leading-snug text-ink">
              {comparison.data.question}
            </p>

            <div className="grid gap-6 lg:grid-cols-2">
              {comparison.data.answers.map((run) => (
                <article key={run.config} className="card flex flex-col p-6">
                  <header className="border-b border-line pb-4">
                    <div className="flex items-baseline gap-3">
                      <span className="font-serif text-lg font-semibold text-ink">
                        {run.config}
                      </span>
                      <span className="text-sm text-ink-muted">{run.description}</span>
                    </div>
                  </header>

                  <p className="mt-4 whitespace-pre-wrap text-[15px] leading-relaxed text-ink">
                    {run.answer}
                  </p>

                  {run.verification ? (
                    <p className="mt-4 rounded border border-line bg-navy-50 px-3 py-2 text-xs text-ink-soft">
                      Verification: <span className="font-medium">{run.verification.verdict}</span>
                      {typeof run.verification.support_rate === "number"
                        ? ` · ${Math.round(run.verification.support_rate * 100)}% of claims supported`
                        : ""}
                      {run.verification.refused ? " · answer withheld" : ""}
                    </p>
                  ) : null}

                  {run.sources.length > 0 ? (
                    <div className="mt-5">
                      <p className="eyebrow mb-2">Sources given to the model</p>
                      <ol className="space-y-1.5 text-xs leading-snug text-ink-soft">
                        {run.sources.map((source) => {
                          const display = displaySource(source);
                          return (
                            <li key={`${run.config}-${source.marker}`} title={display.raw}>
                              <span className="font-semibold text-navy-700">{source.marker}</span>{" "}
                              {display.title}
                              {display.section ? (
                                <span className="text-ink-muted"> · {display.section}</span>
                              ) : null}
                            </li>
                          );
                        })}
                      </ol>
                      {run.omitted_chunks ? (
                        // Retrieval found more than generation was shown. The
                        // gap is the context budget, and it is the difference
                        // between "the system could not find it" and "the
                        // system found it and did not read it".
                        <p className="mt-2 text-xs italic text-ink-muted">
                          {run.omitted_chunks} further passage
                          {run.omitted_chunks === 1 ? " was" : "s were"} retrieved but dropped to
                          fit the context budget.
                        </p>
                      ) : null}
                    </div>
                  ) : !run.sources_recorded ? (
                    <p className="mt-5 text-xs italic text-ink-muted">
                      No source list was recorded for this run.
                    </p>
                  ) : null}

                  <dl className="mt-auto flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-4 text-xs text-ink-muted">
                    <Stat label="Total" value={seconds(run.latency_ms)} />
                    <Stat label="Retrieval" value={seconds(run.retrieval_ms)} />
                    <Stat label="Generation" value={seconds(run.generation_ms)} />
                    {run.iteration_count ? (
                      <Stat label="Agent rounds" value={String(run.iteration_count)} />
                    ) : null}
                  </dl>
                </article>
              ))}
            </div>

            <p className="mt-8 max-w-prose text-sm leading-relaxed text-ink-muted">
              These are recorded runs from the evaluation, not fresh answers. Each configuration
              was run once per question, which is a stated limitation: repeated runs of the same
              question have produced different citations, so a single pair shows what happened,
              not what always happens.
            </p>
          </>
        )}
      </div>
    </>
  );
}

function Header() {
  return (
    <PageHeader
      eyebrow="Evaluation"
      title="Baseline vs proposed"
      lede="The same question, answered by the naive baseline and by the full pipeline, taken from the recorded evaluation runs."
    />
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="inline">{label} </dt>
      <dd className="inline font-medium text-ink-soft">{value}</dd>
    </div>
  );
}

function seconds(ms: number | null): string {
  return typeof ms === "number" ? `${(ms / 1000).toFixed(1)}s` : "—";
}
