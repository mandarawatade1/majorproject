import { cookies } from "next/headers";

import { API_BASE_URL } from "@/lib/api";
import { ADMIN_COOKIE } from "@/lib/admin";

/**
 * Starts an index rebuild, with the session cookie exchanged for a bearer token
 * server-side.
 *
 * The typed `REBUILD` confirmation is *not* enforced here. It is enforced by
 * the API, and adding a second check in the browser would create two places
 * that decide when an index may be destroyed — one of which an attacker
 * controls. The browser's job is to make the requirement visible; the server's
 * job is to be the requirement.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const token = cookies().get(ADMIN_COOKIE)?.value;
  if (!token) return Response.json({ detail: "not signed in" }, { status: 401 });

  const body = await request.text();

  try {
    const upstream = await fetch(`${API_BASE_URL}/admin/index/rebuild`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body,
      cache: "no-store",
    });
    const payload = await upstream.json().catch(() => ({}));
    return Response.json(payload, { status: upstream.status });
  } catch {
    return Response.json(
      { detail: `could not reach the API at ${API_BASE_URL}` },
      { status: 503 },
    );
  }
}
