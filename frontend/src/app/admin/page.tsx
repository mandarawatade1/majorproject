import { redirect } from "next/navigation";
import type { Metadata } from "next";

import { RebuildControl } from "@/components/admin/rebuild-control";
import { SignOutButton } from "@/components/admin/sign-out-button";
import { ApiError } from "@/components/api-error";
import { admin, isSignedIn } from "@/lib/admin";

export const metadata: Metadata = { title: "Console", robots: { index: false } };

export default async function AdminPage() {
  if (!isSignedIn()) redirect("/admin/login");

  const [corpus, evaluations, status, identity] = await Promise.all([
    admin.corpus(),
    admin.evaluations(),
    admin.indexStatus(),
    admin.me(),
  ]);

  // A cookie can outlive the token inside it if the clock drifts, and a
  // deactivated account keeps its cookie until it expires. Either way the API
  // is the authority, so a 401 here means "sign in again", not "show an empty
  // console".
  if (!corpus.ok && (corpus.error === "session expired" || corpus.error === "not signed in")) {
    redirect("/admin/login");
  }

  const agreement = corpus.ok ? corpus.data.corpus_agreement : null;

  return (
    <div className="container-page py-10">
      <header className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Administration</p>
          <h1 className="font-serif text-title text-ink">Console</h1>
          {identity.ok ? (
            <p className="mt-2 text-sm text-ink-muted">
              Signed in as {identity.data.email} ({identity.data.role})
            </p>
          ) : null}
        </div>
        <SignOutButton />
      </header>

      {!corpus.ok ? (
        <ApiError message={corpus.error} />
      ) : (
        <div className="space-y-8">
          {/* Put first because it is the one panel that can tell you the system
              is lying to somebody: when these disagree, the portal serves one
              corpus and the assistant answers from another. */}
          {agreement ? (
            <section
              className={`card p-6 ${agreement.agree ? "border-line" : "border-gold/40 bg-gold-soft/40"}`}
            >
              <h2 className="font-serif text-lg font-semibold text-ink">
                {agreement.agree
                  ? "Database and corpus agree"
                  : "Database and corpus disagree"}
              </h2>
              {agreement.error ? (
                <p className="mt-2 text-sm text-ink-soft">{agreement.error}</p>
              ) : (
                <>
                  <p className="mt-2 text-sm text-ink-soft">
                    Manifest: {agreement.manifest_documents} documents · Database:{" "}
                    {agreement.database_documents}
                    {agreement.difference ? ` · ${agreement.difference}` : ""}
                  </p>
                  {agreement.action ? (
                    <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink">
                      {agreement.action}
                    </p>
                  ) : null}
                </>
              )}
            </section>
          ) : null}

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="card p-6">
              <h2 className="font-serif text-lg font-semibold text-ink">Corpus</h2>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Documents" value={corpus.data.database.documents} />
                <Row label="Real" value={corpus.data.database.real} />
                <Row label="Synthetic" value={corpus.data.database.demo} />
                <Row
                  label="Real share"
                  value={
                    corpus.data.database.real_share !== null
                      ? `${(corpus.data.database.real_share * 100).toFixed(1)}%`
                      : "—"
                  }
                />
                <Row label="Sections" value={corpus.data.database.sections} />
              </dl>
              <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-ink-muted">
                Chunk table: {corpus.data.chunk_table.rows} rows — {corpus.data.chunk_table.note}
              </p>
            </section>

            <section className="card p-6">
              <h2 className="font-serif text-lg font-semibold text-ink">Indexes</h2>
              {corpus.data.index.error ? (
                <p className="mt-3 text-sm text-ink-soft">{corpus.data.index.error}</p>
              ) : (
                <dl className="mt-4 space-y-2 text-sm">
                  {corpus.data.index.dense ? (
                    <Row
                      label={`Dense (${corpus.data.index.dense.name})`}
                      value={`${corpus.data.index.dense.vectors} vectors`}
                    />
                  ) : null}
                  {corpus.data.index.sparse ? (
                    <Row
                      label={`Sparse (${corpus.data.index.sparse.name})`}
                      value={`${corpus.data.index.sparse.entries} entries`}
                    />
                  ) : null}
                </dl>
              )}

              <h3 className="eyebrow mt-6 mb-2">Reference data</h3>
              <dl className="space-y-2 text-sm">
                {Object.entries(corpus.data.reference_data).map(([name, count]) => (
                  <Row key={name} label={name} value={count} />
                ))}
              </dl>
            </section>
          </div>

          <section className="card p-6">
            <h2 className="font-serif text-lg font-semibold text-ink">Evaluation runs</h2>
            {!evaluations.ok ? (
              <p className="mt-3 text-sm text-ink-soft">{evaluations.error}</p>
            ) : evaluations.data.runs.length === 0 ? (
              <p className="mt-3 text-sm text-ink-soft">
                No runs found under {evaluations.data.root}.
              </p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-muted">
                      <th className="pb-2 pr-4 font-medium">Config</th>
                      <th className="pb-2 pr-4 font-medium">Questions</th>
                      <th className="pb-2 pr-4 font-medium">Verification</th>
                      <th className="pb-2 font-medium">Last modified</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {evaluations.data.runs.map((run) => (
                      <tr key={run.config}>
                        <td className="py-2 pr-4 font-medium text-ink">{run.config}</td>
                        <td className="py-2 pr-4 text-ink-soft">{run.questions}</td>
                        <td className="py-2 pr-4 text-ink-soft">
                          {run.verification_verdicts
                            ? Object.entries(run.verification_verdicts)
                                .map(([verdict, count]) => `${verdict} ${count}`)
                                .join(", ")
                            : "—"}
                        </td>
                        <td className="py-2 text-xs text-ink-muted">
                          {run.modified.slice(0, 16).replace("T", " ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {status.ok ? <RebuildControl status={status.data} /> : null}

          <section className="card border-dashed p-6">
            <h2 className="eyebrow mb-2">Not in this console</h2>
            <p className="max-w-prose text-sm leading-relaxed text-ink-soft">
              Crawling, content editing and launching evaluation runs are deliberately absent —
              the API has no endpoints for them, and an evaluation run occupies the machine for
              hours, which is not something to start from a web page. Those remain command-line
              operations, documented in the README.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="capitalize text-ink-soft">{label.replace(/_/g, " ")}</dt>
      <dd className="font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
