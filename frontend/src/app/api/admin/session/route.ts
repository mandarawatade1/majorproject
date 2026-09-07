import { cookies } from "next/headers";

import { API_BASE_URL } from "@/lib/api";

/**
 * The admin session, held in an httpOnly cookie.
 *
 * The obvious approach — take the token pair from `/auth/login` and keep it in
 * `localStorage` — puts a credential that grants administrative access into a
 * place every script on the page can read. One cross-site scripting hole
 * anywhere in the portal would then hand an attacker an admin token, and this
 * application renders content that ultimately comes from a crawler.
 *
 * Instead the browser never sees the token. This route exchanges credentials
 * with FastAPI server-side and stores the access token in an httpOnly,
 * sameSite cookie; server components read it back and call the API with it.
 * JavaScript in the page cannot read it, so an injected script cannot steal it.
 *
 * The trade-off is honest: the refresh token is discarded rather than stored,
 * so a session lasts exactly as long as one access token — thirty minutes by
 * default — and then requires signing in again. For a console used
 * occasionally by one administrator that is the right side of the trade.
 */
export const dynamic = "force-dynamic";

const COOKIE = "pce_admin";

export async function POST(request: Request): Promise<Response> {
  let credentials: unknown;
  try {
    credentials = await request.json();
  } catch {
    return Response.json({ detail: "expected a JSON body" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: `could not reach the API at ${API_BASE_URL}` },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // Passed through unchanged. The API answers every login failure with one
    // message on purpose — distinguishing "no such account" from "wrong
    // password" would hand back the account-enumeration oracle it avoids.
    const payload = (await upstream.json().catch(() => ({}))) as { detail?: string };
    return Response.json(
      { detail: payload.detail ?? "sign-in failed" },
      { status: upstream.status },
    );
  }

  const tokens = (await upstream.json()) as { access_token: string; expires_in: number };

  cookies().set({
    name: COOKIE,
    value: tokens.access_token,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    // Matches the token's own lifetime, so the cookie cannot outlive the
    // credential it carries and leave the console appearing signed in.
    maxAge: tokens.expires_in,
    secure: process.env.NODE_ENV === "production",
  });

  return Response.json({ ok: true });
}

export async function DELETE(): Promise<Response> {
  cookies().delete(COOKIE);
  return Response.json({ ok: true });
}
