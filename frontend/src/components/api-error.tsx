import { API_BASE_URL } from "@/lib/api";

/**
 * Shown in place of content when the backend could not be reached.
 *
 * It names the address it tried and the command that starts the service,
 * because in this project's realistic failure — a demo where the API container
 * is still booting — the person reading the screen is the person who can fix
 * it, and "Something went wrong" would waste their next five minutes.
 */
export function ApiError({ message }: { message: string }) {
  return (
    <div className="card border-gold/30 bg-gold-soft/40 p-6">
      <p className="font-semibold text-ink">This section could not be loaded.</p>
      <p className="mt-2 text-sm text-ink-soft">{message}</p>
      <p className="mt-4 text-sm text-ink-muted">
        The portal reads from{" "}
        <code className="rounded bg-white px-1.5 py-0.5 text-[13px] text-ink">{API_BASE_URL}</code>. If
        the stack is not running, start it with{" "}
        <code className="rounded bg-white px-1.5 py-0.5 text-[13px] text-ink">docker compose up -d</code>.
      </p>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-white/60 p-10 text-center">
      <p className="font-medium text-ink">{title}</p>
      {detail ? <p className="mx-auto mt-2 max-w-prose text-sm text-ink-muted">{detail}</p> : null}
    </div>
  );
}
