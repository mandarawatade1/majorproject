import Link from "next/link";
import type { Metadata } from "next";

import { ApiError, EmptyState } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Departments" };

export default async function DepartmentsPage() {
  const result = await api.departments();

  return (
    <>
      <PageHeader
        eyebrow="Academics"
        title="Departments"
        lede="Each department below is described from the college's own published pages. Open one to see the programmes it runs."
      />

      <div className="container-page py-12">
        {result.error ? (
          <ApiError message={result.error} />
        ) : result.data.items.length === 0 ? (
          <EmptyState
            title="No departments have been loaded."
            detail="Run `docker compose exec api python -m app.seed reference` to populate them."
          />
        ) : (
          <ul className="grid gap-5 sm:grid-cols-2">
            {result.data.items.map((department) => (
              <li key={department.id}>
                <Link
                  href={`/departments/${department.slug}`}
                  className="card-interactive flex h-full flex-col p-7"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="eyebrow">{department.code}</span>
                    {department.is_demo ? <DemoBadge /> : null}
                  </div>
                  <h2 className="mt-3 font-serif text-xl font-semibold leading-snug text-ink">
                    {department.name}
                  </h2>
                  {department.about ? (
                    <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-ink-soft">
                      {department.about}
                    </p>
                  ) : null}
                  <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-2 text-sm text-ink-muted">
                    {department.established_year ? (
                      <div>
                        <dt className="inline">Established </dt>
                        <dd className="inline font-medium text-ink-soft">
                          {department.established_year}
                        </dd>
                      </div>
                    ) : null}
                    {department.hod_name ? (
                      <div>
                        <dt className="inline">Head </dt>
                        <dd className="inline font-medium text-ink-soft">{department.hod_name}</dd>
                      </div>
                    ) : null}
                  </dl>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
