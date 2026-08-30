import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { ApiError } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { levelLabel } from "@/lib/types";

type Props = { params: { slug: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const result = await api.department(params.slug);
  return { title: result.ok ? result.data.name : "Department" };
}

export default async function DepartmentPage({ params }: Props) {
  const result = await api.department(params.slug);

  if (!result.ok) {
    // A missing department is a 404, not an outage. The two look identical to
    // a visitor otherwise, and only one of them is worth telling them how to
    // fix.
    if (result.error === "not found") notFound();
    return (
      <div className="container-page py-12">
        <ApiError message={result.error} />
      </div>
    );
  }

  const department = result.data;

  return (
    <>
      <PageHeader
        eyebrow={department.code}
        title={department.name}
        lede={department.about ?? undefined}
      >
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm text-ink-muted">
          {department.established_year ? <span>Established {department.established_year}</span> : null}
          {department.hod_name ? <span>Head of department: {department.hod_name}</span> : null}
          {department.email ? (
            <a href={`mailto:${department.email}`} className="text-navy-700 link-underline">
              {department.email}
            </a>
          ) : null}
          {department.is_demo ? <DemoBadge /> : null}
        </div>
      </PageHeader>

      <div className="container-page grid gap-12 py-12 lg:grid-cols-[1fr_320px]">
        <div>
          <h2 className="font-serif text-xl font-semibold text-ink">Programmes</h2>
          {department.programs.length === 0 ? (
            <p className="mt-3 text-sm text-ink-muted">
              No programmes are recorded against this department.
            </p>
          ) : (
            <ul className="mt-5 space-y-4">
              {department.programs.map((program) => (
                <li key={program.id} className="card p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <span className="eyebrow">{levelLabel(program.level)}</span>
                      <h3 className="mt-2 font-serif text-lg font-semibold text-ink">
                        {program.name}
                      </h3>
                    </div>
                    {program.is_demo ? <DemoBadge /> : null}
                  </div>
                  <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 text-sm text-ink-muted">
                    {program.intake ? (
                      <div>
                        <dt className="inline">Sanctioned intake </dt>
                        <dd className="inline font-medium text-ink-soft">{program.intake}</dd>
                      </div>
                    ) : null}
                    {program.duration_years ? (
                      <div>
                        <dt className="inline">Duration </dt>
                        <dd className="inline font-medium text-ink-soft">
                          {program.duration_years} years
                        </dd>
                      </div>
                    ) : null}
                  </dl>
                  {program.curriculum_url ? (
                    <a
                      href={program.curriculum_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-4 inline-block text-sm font-medium text-navy-700 link-underline"
                    >
                      Curriculum
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        <aside className="space-y-8">
          {department.vision ? (
            <section>
              <h2 className="eyebrow mb-2">Vision</h2>
              <p className="text-sm leading-relaxed text-ink-soft">{department.vision}</p>
            </section>
          ) : null}
          {department.mission ? (
            <section>
              <h2 className="eyebrow mb-2">Mission</h2>
              <p className="text-sm leading-relaxed text-ink-soft">{department.mission}</p>
            </section>
          ) : null}

          {/* Provenance, on the page rather than in a footnote. The point of
              this project is that a reader can check a claim, which requires
              knowing where the claim came from. */}
          {department.source_url ? (
            <section>
              <h2 className="eyebrow mb-2">Source</h2>
              <a
                href={department.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="break-words text-sm text-navy-700 link-underline"
              >
                {department.source_url}
              </a>
            </section>
          ) : null}

          <Link href="/departments" className="inline-block text-sm font-medium text-navy-700 link-underline">
            ← All departments
          </Link>
        </aside>
      </div>
    </>
  );
}
