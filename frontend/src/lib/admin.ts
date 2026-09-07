import { cookies } from "next/headers";

import { API_BASE_URL } from "@/lib/api";
import type { Result } from "@/lib/api";

/**
 * Server-side calls to the admin API, authenticated from the session cookie.
 *
 * Every function here reads the cookie itself rather than taking a token as an
 * argument. That is deliberate: a token passed around as a parameter is a
 * token that can be logged, serialised into a server-component payload, or
 * handed to a client component by accident. Keeping it inside this module
 * means the only thing that ever crosses to the browser is the data.
 */

const COOKIE = "pce_admin";

export const ADMIN_COOKIE = COOKIE;

export interface CorpusAgreement {
  manifest_documents?: number;
  database_documents?: number;
  agree?: boolean;
  difference?: string;
  action?: string;
  error?: string;
}

export interface AdminCorpus {
  database: {
    documents: number;
    real: number;
    demo: number;
    real_share: number | null;
    sections: number;
    by_category: Record<string, number>;
  };
  corpus_agreement: CorpusAgreement;
  index: {
    dense?: { name: string; vectors: number };
    sparse?: { name: string; entries: number };
    error?: string;
  };
  chunk_table: { rows: number; note: string };
  reference_data: Record<string, number>;
}

export interface EvaluationRun {
  config: string;
  questions: number;
  has_summary: boolean;
  modified: string;
  verification_verdicts: Record<string, number> | null;
  agent_stop_reasons: Record<string, number> | null;
}

export interface RebuildStatus {
  running: boolean;
  config: string | null;
  started_at: string | null;
  finished_at: string | null;
  result: string | null;
  error: string | null;
}

export function adminToken(): string | undefined {
  return cookies().get(COOKIE)?.value;
}

export function isSignedIn(): boolean {
  return Boolean(adminToken());
}

async function adminGet<T>(path: string): Promise<Result<T>> {
  const token = adminToken();
  if (!token) return { ok: false, error: "not signed in" };

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });

    if (response.status === 401) return { ok: false, error: "session expired" };
    if (response.status === 403) return { ok: false, error: "this account is not an administrator" };
    if (!response.ok) return { ok: false, error: `the API answered ${response.status}` };
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, error: `could not reach the API at ${API_BASE_URL}` };
  }
}

export const admin = {
  corpus: () => adminGet<AdminCorpus>("/admin/corpus"),
  evaluations: () => adminGet<{ root: string; runs: EvaluationRun[] }>("/admin/evaluations"),
  indexStatus: () => adminGet<RebuildStatus>("/admin/index/status"),
  me: () => adminGet<{ id: string; email: string; role: string }>("/auth/me"),
};
