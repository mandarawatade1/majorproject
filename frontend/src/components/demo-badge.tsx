/**
 * The single most important component in this portal.
 *
 * Roughly 5% of the corpus is synthetic, authored where no public source
 * existed. The project's standing rule is that `is_demo` travels from the
 * parser through the manifest, the database, the chunk, the index and the
 * citation — and it has to be visible at the end of that chain or the whole
 * apparatus is decorative. Anything rendered from a record carrying
 * `is_demo: true` shows this, without exception.
 *
 * It is a `<span>` with real text rather than a coloured dot, because a colour
 * alone is invisible to a screen reader and to a colour-blind examiner.
 */
export function DemoBadge({ reason }: { reason?: string | null }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded border border-gold/30 bg-gold-soft px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-gold"
      title={reason ?? "Synthetic record, authored for demonstration"}
    >
      Demo data
    </span>
  );
}
