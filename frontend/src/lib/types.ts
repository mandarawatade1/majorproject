/**
 * Shapes returned by the FastAPI portal endpoints.
 *
 * Written by hand against `backend/app/api/routes/portal.py` rather than
 * generated, because the endpoints return plain dictionaries assembled in the
 * route functions — there is no response model to generate from. That makes
 * these types a *claim* about the API rather than a guarantee, so every field
 * the portal actually renders is treated as possibly absent where the backend
 * uses `getattr(..., None)`.
 */

export interface Paged<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface Department {
  id: string;
  code: string;
  name: string;
  slug: string;
  established_year: number | null;
  hod_name: string | null;
  about: string | null;
  email: string | null;
  source_url: string | null;
  is_demo: boolean;
}

export interface Program {
  id: string;
  name: string;
  slug: string;
  level: string;
  department_id?: string | null;
  intake: number | null;
  duration_years: number | null;
  description?: string | null;
  curriculum_url: string | null;
  source_url?: string | null;
  is_demo: boolean;
}

export interface DepartmentDetail extends Department {
  vision: string | null;
  mission: string | null;
  phone: string | null;
  faculty_count: number;
  programs: Program[];
}

export interface CorpusDocument {
  id: string;
  doc_id: string;
  title: string;
  category: string;
  source_type: string;
  source_url: string | null;
  is_demo: boolean;
  demo_reason: string | null;
}

export interface CorpusStats {
  documents: number;
  real: number;
  demo: number;
  real_share: number | null;
  by_category: Record<string, number>;
}

/** Human labels for the programme levels the API returns as bare strings. */
export const LEVEL_LABELS: Record<string, string> = {
  btech: "B.Tech",
  mtech: "M.Tech",
  phd: "Ph.D.",
  diploma: "Diploma",
  certificate: "Certificate",
};

export function levelLabel(level: string): string {
  return LEVEL_LABELS[level] ?? level;
}

/** Next hands search params as `string | string[] | undefined`. Take the first. */
export type SearchParams = { [key: string]: string | string[] | undefined };

export function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
