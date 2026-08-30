import Link from "next/link";
import type { Metadata } from "next";

import { ApiError, EmptyState } from "@/components/api-error";
import { DemoBadge } from "@/components/demo-badge";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { firstParam, type SearchParams } from "@/lib/types";

export const metadata: Metadata = { title: "Knowledge base" };

const PAGE_SIZE = 25;

type Props = { searchParams: SearchParams };

/**
 * Everything the assistant can draw on, browsable.
 *
 * The point is falsifiability. Ask PCE claims its answers come only from these
 * documents; this is where a visitor checks that claim, sees how much of the
 * corpus is synthetic, and follows any document back to the page it was
 * collected from.
 */
export default async function ExplorePage({ searchParams }: Props) {
  const search = (firstParam(searchParams.q) ?? "").trim();
  const category = firstParam(searchParams.category) ?? "";
  const page = Math.max(1, Number.parseInt(firstParam(searchParams.page) ?? "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const [stats, documents] = await Promise.all([
    api.corpusStats(),
    api.documents({
      category: category || undefined,
      search: search.length >= 2 ? search : undefined,
      limit: PAGE_SIZE,
      offset,
    }),
  ]);

  const total = documents.ok ? documents.data.total : 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const categories = stats.ok
    ? Object.entries(stats.data.by_category).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <>
      <PageHeader
        eyebrow="Knowledge base"
        title="What the assistant knows"
        lede="Every document Ask PCE can draw on. Nothing outside this set is used to answer a question, and anything synthetic is marked."
      >
        <form action="/explore" method="get" role="search" className="flex max-w-md gap-2">
          <label htmlFor="q" className="sr-only">
            Search documents by title
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={search}
            placeholder="Search titles"
            minLength={2}
            className="w-full rounded-md border border-line bg-white px-4 py-2.5 text-sm text-ink placeholder:text-ink-muted"
          />
          {/* Preserved so searching inside a category does not silently widen
              the search to the whole corpus. */}
          {category ? <input type="hidden" name="category" value={category} /> : null}
          <button
            type="submit"
            className="rounded-md bg-navy-900 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-700"
          >
            Search
          </button>
        </form>
      </PageHeader>

      <div className="container-page grid gap-10 py-10 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside>
          <h2 className="eyebrow mb-3">Categories</h2>
          <ul className="space-y-1 text-sm">
            <li>
              <CategoryLink label="All" href={hrefFor(search, "")} active={!category} count={stats.ok ? stats.data.documents : null} />
            </li>
            {categories.map(([name, count]) => (
              <li key={name}>
                <CategoryLink
                  label={name.replace(/_/g, " ")}
                  href={hrefFor(search, name)}
                  active={category === name}
                  count={count}
                />
              </li>
            ))}
          </ul>
        </aside>

        <div className="min-w-0">
          {!documents.ok ? (
            <ApiError message={documents.error} />
          ) : documents.data.items.length === 0 ? (
            <EmptyState
              title="Nothing matches those filters."
              detail="Search matches document titles only."
            />
          ) : (
            <>
              <p className="mb-5 text-sm text-ink-muted">
                {total} document{total === 1 ? "" : "s"} · showing {offset + 1}–
                {Math.min(offset + documents.data.items.length, total)}
              </p>

              <ul className="divide-y divide-line border-y border-line">
                {documents.data.items.map((document) => (
                  <li key={document.id} className="py-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="max-w-prose font-medium leading-snug text-ink">
                        {document.title}
                      </h3>
                      {document.is_demo ? <DemoBadge reason={document.demo_reason} /> : null}
                    </div>
                    <p className="mt-1 text-xs uppercase tracking-wide text-ink-muted">
                      {document.category.replace(/_/g, " ")} · {document.source_type}
                    </p>
                    {document.source_url ? (
                      <a
                        href={document.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="mt-1 inline-block break-all text-xs text-navy-700 link-underline"
                      >
                        {document.source_url}
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>

              {lastPage > 1 ? (
                <nav aria-label="Pagination" className="mt-8 flex items-center justify-between">
                  <PageLink href={hrefFor(search, category, page - 1)} disabled={page <= 1} label="← Previous" />
                  <span className="text-sm text-ink-muted">
                    Page {page} of {lastPage}
                  </span>
                  <PageLink href={hrefFor(search, category, page + 1)} disabled={page >= lastPage} label="Next →" />
                </nav>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function hrefFor(search: string, category: string, page = 1): string {
  const params = new URLSearchParams();
  if (search) params.set("q", search);
  if (category) params.set("category", category);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/explore?${query}` : "/explore";
}

function CategoryLink({
  label,
  href,
  active,
  count,
}: {
  label: string;
  href: string;
  active: boolean;
  count: number | null;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={`flex items-baseline justify-between gap-2 rounded px-2 py-1.5 capitalize transition-colors ${
        active ? "bg-navy-100 font-medium text-navy-700" : "text-ink-soft hover:bg-navy-50"
      }`}
    >
      <span>{label}</span>
      {count !== null ? <span className="text-xs tabular-nums text-ink-muted">{count}</span> : null}
    </Link>
  );
}

function PageLink({ href, disabled, label }: { href: string; disabled: boolean; label: string }) {
  if (disabled) return <span className="text-sm text-ink-muted opacity-50">{label}</span>;
  return (
    <Link href={href} className="text-sm font-medium text-navy-700 link-underline">
      {label}
    </Link>
  );
}
