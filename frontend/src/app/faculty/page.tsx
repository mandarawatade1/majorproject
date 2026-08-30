import Link from "next/link";
import type { Metadata } from "next";

import { ApiError, EmptyState } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { firstParam, type SearchParams } from "@/lib/types";

export const metadata: Metadata = { title: "Faculty" };

const PAGE_SIZE = 24;

type Props = { searchParams: SearchParams };

/**
 * Served from the document corpus, not from a `faculty` table.
 *
 * The schema has one, but nothing populates it — the crawled directory pages
 * were never parsed into structured staff records. Rather than ship an empty
 * page where a college site has its most-visited one, this lists the faculty
 * pages themselves and links each to its source. The page says so plainly
 * instead of implying a directory it does not have.
 */
export default async function FacultyPage({ searchParams }: Props) {
  const search = (firstParam(searchParams.q) ?? "").trim();
  const page = Math.max(1, Number.parseInt(firstParam(searchParams.page) ?? "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const result = await api.documents({
    category: "faculty",
    search: search.length >= 2 ? search : undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const total = result.ok ? result.data.total : 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader
        eyebrow="People"
        title="Faculty"
        lede="Faculty pages published by the college, as held in this portal's knowledge base. Each entry links to the page it was collected from."
      >
        <form action="/faculty" method="get" role="search" className="flex max-w-md gap-2">
          <label htmlFor="q" className="sr-only">
            Search faculty pages by name
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={search}
            placeholder="Search by name"
            minLength={2}
            className="w-full rounded-md border border-line bg-white px-4 py-2.5 text-sm text-ink placeholder:text-ink-muted"
          />
          <button
            type="submit"
            className="rounded-md bg-navy-900 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-700"
          >
            Search
          </button>
        </form>
      </PageHeader>

      <div className="container-page py-12">
        {!result.ok ? (
          <ApiError message={result.error} />
        ) : result.data.items.length === 0 ? (
          <EmptyState
            title={search ? `Nothing matches “${search}”.` : "No faculty pages have been loaded."}
            detail={
              search
                ? "Search matches page titles only, so try a surname on its own."
                : "Run `docker compose exec api python -m app.seed corpus` to load the knowledge base."
            }
          />
        ) : (
          <>
            <p className="mb-6 text-sm text-ink-muted">
              {total} page{total === 1 ? "" : "s"}
              {search ? ` matching “${search}”` : ""} · showing {offset + 1}–
              {Math.min(offset + result.data.items.length, total)}
            </p>

            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {result.data.items.map((document) => (
                <li key={document.id} className="card flex h-full flex-col p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-serif text-[17px] font-semibold leading-snug text-ink">
                      {document.title}
                    </h2>
                    {document.is_demo ? <DemoBadge reason={document.demo_reason} /> : null}
                  </div>
                  {document.source_url ? (
                    <a
                      href={document.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-auto pt-4 text-sm font-medium text-navy-700 link-underline"
                    >
                      View source page
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>

            {lastPage > 1 ? (
              <nav aria-label="Pagination" className="mt-10 flex items-center justify-between">
                <PageLink
                  href={buildHref(search, page - 1)}
                  disabled={page <= 1}
                  label="← Previous"
                />
                <span className="text-sm text-ink-muted">
                  Page {page} of {lastPage}
                </span>
                <PageLink
                  href={buildHref(search, page + 1)}
                  disabled={page >= lastPage}
                  label="Next →"
                />
              </nav>
            ) : null}
          </>
        )}
      </div>
    </>
  );
}

function buildHref(search: string, page: number): string {
  const params = new URLSearchParams();
  if (search) params.set("q", search);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/faculty?${query}` : "/faculty";
}

function PageLink({ href, disabled, label }: { href: string; disabled: boolean; label: string }) {
  if (disabled) {
    return <span className="text-sm text-ink-muted opacity-50">{label}</span>;
  }
  return (
    <Link href={href} className="text-sm font-medium text-navy-700 link-underline">
      {label}
    </Link>
  );
}
