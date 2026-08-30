import Link from "next/link";

import { ApiError } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { api } from "@/lib/api";

export default async function HomePage() {
  const [departments, stats] = await Promise.all([api.departments(), api.corpusStats()]);

  return (
    <>
      <section className="border-b border-line bg-white">
        <div className="container-page py-16 sm:py-24">
          <p className="eyebrow mb-4">Autonomous · Affiliated to University of Mumbai</p>
          <h1 className="max-w-4xl font-serif text-display text-ink">
            Everything the college publishes, in one place you can actually search.
          </h1>
          <p className="mt-6 max-w-prose text-lg leading-relaxed text-ink-soft">
            This portal is built over a retrieval-augmented knowledge base assembled from
            the college&rsquo;s own public pages and documents. Every figure it shows can be
            traced back to the page it came from.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/departments"
              className="rounded-md bg-navy-900 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-navy-700"
            >
              Browse departments
            </Link>
            <Link
              href="/programs"
              className="rounded-md border border-line bg-white px-5 py-3 text-sm font-semibold text-ink transition-colors hover:border-navy-200 hover:bg-navy-50"
            >
              See programmes
            </Link>
          </div>
        </div>
      </section>

      {/* The corpus counts, published rather than asserted. The project claims a
          predominantly real corpus; showing the split lets a visitor check it
          instead of taking it on trust. */}
      {stats.data ? (
        <section aria-labelledby="corpus-heading" className="border-b border-line bg-navy-50">
          <div className="container-page py-10">
            <h2 id="corpus-heading" className="eyebrow mb-5">
              What this portal knows
            </h2>
            <dl className="grid gap-6 sm:grid-cols-3">
              <div>
                <dt className="text-sm text-ink-muted">Source documents</dt>
                <dd className="mt-1 font-serif text-3xl text-ink">{stats.data.documents}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-muted">Drawn from pce.ac.in</dt>
                {/* The explicit {" "} matters: a margin separates these
                    visually but leaves no whitespace in the text, so a screen
                    reader announces "72694.9%" as one number. */}
                <dd className="mt-1 font-serif text-3xl text-ink">
                  {stats.data.real}{" "}
                  {stats.data.real_share !== null ? (
                    <span className="align-middle font-sans text-base text-ink-muted">
                      ({(stats.data.real_share * 100).toFixed(1)}% of the corpus)
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-2 text-sm text-ink-muted">
                  Synthetic <DemoBadge />
                </dt>
                <dd className="mt-1 font-serif text-3xl text-ink">{stats.data.demo}</dd>
              </div>
            </dl>
          </div>
        </section>
      ) : null}

      <section className="container-page py-14">
        <div className="mb-8 flex items-end justify-between gap-4">
          <h2 className="font-serif text-title text-ink">Departments</h2>
          <Link href="/departments" className="text-sm font-medium text-navy-700 link-underline">
            View all
          </Link>
        </div>

        {departments.error ? (
          <ApiError message={departments.error} />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {departments.data.items.slice(0, 6).map((department) => (
              <li key={department.id}>
                <Link
                  href={`/departments/${department.slug}`}
                  className="card-interactive block h-full p-6"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="eyebrow">{department.code}</span>
                    {department.is_demo ? <DemoBadge /> : null}
                  </div>
                  <h3 className="mt-3 font-serif text-lg font-semibold leading-snug text-ink">
                    {department.name}
                  </h3>
                  {department.about ? (
                    <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-ink-soft">
                      {department.about}
                    </p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
