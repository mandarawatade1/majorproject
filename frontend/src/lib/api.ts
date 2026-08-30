/**
 * The portal's only route to the backend.
 *
 * Two decisions worth stating.
 *
 * **Failure is a value, not an exception.** Every call returns
 * `{ data }` or `{ error }`. A portal whose API is briefly down should render
 * a page that says so, not a stack trace or a blank screen — this is a system
 * that gets demonstrated live on a laptop running five containers, and the
 * realistic failure is "the API is still starting", which deserves a sentence
 * rather than a crash.
 *
 * **Nothing is cached.** The corpus and its counts change whenever the seed
 * runs, and a portal showing yesterday's document count while the admin panel
 * shows today's is exactly the drift this project has spent two phases
 * chasing. Correctness beats a fast second paint here.
 */

import type {
  CorpusDocument,
  CorpusStats,
  Department,
  DepartmentDetail,
  Paged,
  Program,
} from "./types";

const BASE =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

/**
 * Discriminated on a literal `ok`, not on whether `error` is set.
 *
 * The obvious shape — `{ data: T } | { error: string }` — does not narrow.
 * `if (result.error)` is a truthiness test, and `""` is a valid `string`, so
 * TypeScript cannot rule out the error branch and `data` stays possibly
 * undefined at every use site. A literal `true`/`false` tag is the only thing
 * the compiler can eliminate a branch on.
 */
export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<Result<T>> {
  const url = new URL(`${BASE}${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }

  try {
    const response = await fetch(url.toString(), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });

    if (response.status === 404) return { ok: false, error: "not found" };
    if (!response.ok) {
      return { ok: false, error: `the API answered ${response.status} for ${path}` };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch {
    // Almost always the API container not being up yet. Naming the address is
    // the single most useful thing to put on the screen, because the fix is
    // either starting it or correcting API_BASE_URL.
    return { ok: false, error: `could not reach the API at ${BASE}` };
  }
}

// The portal router is mounted with `APIRouter(tags=["portal"])` — no prefix of
// its own — so its routes sit directly under the API prefix. There is no
// `/portal` segment, however much the module name suggests one.
export const api = {
  departments: () => get<{ total: number; items: Department[] }>("/departments"),

  department: (slug: string) => get<DepartmentDetail>(`/departments/${encodeURIComponent(slug)}`),

  programs: (level?: string) => get<{ total: number; items: Program[] }>("/programs", { level }),

  corpusStats: () => get<CorpusStats>("/corpus/stats"),

  /**
   * Faculty pages are served from the document corpus rather than a `faculty`
   * table. The table exists in the schema but nothing populates it; the
   * crawled directory pages do, and pretending otherwise would mean an empty
   * page where a university site always has its most-visited one.
   */
  documents: (options: {
    category?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) => get<Paged<CorpusDocument>>("/corpus/documents", options),
};

export const API_BASE_URL = BASE;
