import Link from "next/link";
import type { Metadata } from "next";

import { ApiError, EmptyState } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { firstParam, levelLabel, type SearchParams } from "@/lib/types";

export const metadata: Metadata = { title: "Programmes" };

const LEVELS = ["btech", "mtech", "phd", "diploma", "certificate"];

type Props = { searchParams: SearchParams };

export default async function ProgramsPage({ searchParams }: Props) {
  // Validated against the known set rather than passed through: the value
  // reaches a SQL filter, and an unrecognised level should mean "all" rather
  // than an empty page or a 422 from the API.
  const requested = firstParam(searchParams.level);
  const level = requested && LEVELS.includes(requested) ? requested : undefined;
  const result = await api.programs(level);

  return (
    <>
      <PageHeader
        eyebrow="Academics"
        title="Programmes"
        lede="Undergraduate and postgraduate programmes, with sanctioned intake where the college publishes it."
      >
        {/* Links rather than a client-side filter: the filter state lives in
            the URL, so it survives a reload, can be shared, and needs no
            JavaScript to work. */}
        <nav aria-label="Filter by level" className="flex flex-wrap gap-2">
          <FilterLink href="/programs" active={!level} label="All" />
          {LEVELS.map((value) => (
            <FilterLink
              key={value}
              href={`/programs?level=${value}`}
              active={level === value}
              label={levelLabel(value)}
            />
          ))}
        </nav>
      </PageHeader>

      <div className="container-page py-12">
        {!result.ok ? (
          <ApiError message={result.error} />
        ) : result.data.items.length === 0 ? (
          <EmptyState
            title={level ? `No ${levelLabel(level)} programmes are recorded.` : "No programmes have been loaded."}
            detail={level ? "Try another level, or view all programmes." : undefined}
          />
        ) : (
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {result.data.items.map((program) => (
              <li key={program.id} className="card flex h-full flex-col p-6">
                <div className="flex items-start justify-between gap-3">
                  <span className="eyebrow">{levelLabel(program.level)}</span>
                  {program.is_demo ? <DemoBadge /> : null}
                </div>
                <h2 className="mt-3 font-serif text-lg font-semibold leading-snug text-ink">
                  {program.name}
                </h2>
                {program.description ? (
                  <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-ink-soft">
                    {program.description}
                  </p>
                ) : null}
                <dl className="mt-auto flex flex-wrap gap-x-6 gap-y-1 pt-5 text-sm text-ink-muted">
                  {program.intake ? (
                    <div>
                      <dt className="inline">Intake </dt>
                      <dd className="inline font-medium text-ink-soft">{program.intake}</dd>
                    </div>
                  ) : null}
                  {program.duration_years ? (
                    <div>
                      <dt className="inline">Duration </dt>
                      <dd className="inline font-medium text-ink-soft">
                        {program.duration_years} yr
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

function FilterLink({ href, active, label }: { href: string; active: boolean; label: string }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "border-navy-900 bg-navy-900 text-white"
          : "border-line bg-white text-ink-soft hover:border-navy-200 hover:text-ink"
      }`}
    >
      {label}
    </Link>
  );
}
