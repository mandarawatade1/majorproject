"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { RebuildStatus } from "@/lib/admin";

/**
 * The one destructive control in the console.
 *
 * It asks for the word REBUILD to be typed, which is the same requirement the
 * API enforces. The point is not the friction — it is that a rebuild takes
 * several minutes, competes for memory with everything else on this hardware,
 * and destroys an index the evaluation was computed against. A control that
 * can do that from a single click is a control that will eventually be clicked
 * by accident.
 */
export function RebuildControl({ status }: { status: RebuildStatus }) {
  const router = useRouter();
  const [config, setConfig] = useState("C3");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch("/api/admin/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config, confirm, limit: 0 }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: string;
        note?: string;
      };
      setMessage(response.ok ? (payload.note ?? "rebuild started") : (payload.detail ?? "refused"));
      if (response.ok) {
        setConfirm("");
        router.refresh();
      }
    } catch {
      setMessage("could not reach the portal's server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card border-gold/30 p-6">
      <h2 className="font-serif text-lg font-semibold text-ink">Rebuild the index</h2>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-soft">
        Re-chunks and re-embeds the whole corpus for the selected configuration&rsquo;s chunking
        strategy. This destroys the existing index for that strategy and takes several minutes.
        The evaluation in Chapter 4 was computed against the structure-aware index.
      </p>

      {status.running ? (
        <p className="mt-4 rounded border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-ink">
          A rebuild of <span className="font-semibold">{status.config}</span> is running, started{" "}
          {status.started_at}.
        </p>
      ) : (
        <form onSubmit={start} className="mt-5 flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="config" className="mb-1.5 block text-xs font-medium text-ink-soft">
              Configuration
            </label>
            <select
              id="config"
              value={config}
              onChange={(event) => setConfig(event.target.value)}
              className="rounded-md border border-line bg-white px-3 py-2 text-sm text-ink"
            >
              {["C0", "C1", "C2", "C3", "C4", "C5"].map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="confirm" className="mb-1.5 block text-xs font-medium text-ink-soft">
              Type REBUILD to confirm
            </label>
            <input
              id="confirm"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              placeholder="REBUILD"
              className="rounded-md border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-muted"
            />
          </div>

          <button
            type="submit"
            disabled={busy || confirm !== "REBUILD"}
            className="rounded-md bg-navy-900 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-navy-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Starting…" : "Rebuild"}
          </button>
        </form>
      )}

      {message ? <p className="mt-4 text-sm text-ink-soft">{message}</p> : null}

      {status.finished_at && !status.running ? (
        <p className="mt-4 text-xs text-ink-muted">
          Last rebuild ({status.config}) finished {status.finished_at}
          {status.result ? ` — ${status.result}` : ""}
          {status.error ? ` — failed: ${status.error}` : ""}
        </p>
      ) : null}
    </section>
  );
}
