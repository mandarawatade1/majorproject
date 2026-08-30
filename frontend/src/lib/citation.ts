/**
 * Accepts anything carrying a label and a URL, so the live answer stream and
 * the recorded evaluation runs share one implementation. Two prettifiers over
 * one label format would drift.
 */
interface Labelled {
  label: string;
  url: string | null;
}

/**
 * Make a citation label readable, without changing what it refers to.
 *
 * The backend builds labels as `{document_title} > {heading} > page N`, and
 * the logic is right. The trouble is `document_title`: for a crawled PDF it is
 * derived from the URL path at parse time, so
 * `.../uploads/2023/07/1-Courses-Intake.pdf` becomes the document title
 * "Wp Content Uploads 2023 07 1 Courses Intake.Pdf" — accurate, and unreadable
 * beside an answer.
 *
 * **This is deliberately a display fix and not a data fix.** Correcting the
 * title at parse time would mean re-parsing the corpus, which re-chunks it,
 * which invalidates the index every evaluation run was computed against. A
 * cosmetic problem is not worth seven configurations and 140 questions.
 *
 * So: the same document, the same section, the same page — spelled better. The
 * unmodified label is kept and shown on hover, so what the pipeline actually
 * recorded stays inspectable rather than being quietly replaced.
 */
export interface DisplaySource {
  title: string;
  section: string | null;
  raw: string;
}

export function displaySource(source: Labelled): DisplaySource {
  const raw = source.label;

  const parts = raw
    .replace(/\s*\[DEMO DATA\]\s*$/i, "")
    .split(">")
    .map((part) => part.trim())
    .filter(Boolean);

  // `page N` is dropped from the section path because the page is rendered as
  // its own field; leaving it here would print it twice.
  const section = parts.slice(1).filter((part) => !/^page\s+\d+$/i.test(part));

  const fallback = parts[0] ?? raw;
  const title = isPdf(source.url) ? (titleFromUrl(source.url) ?? fallback) : fallback;

  return {
    title,
    section: section.length > 0 ? section.join(" › ") : null,
    raw,
  };
}

function isPdf(url: string | null): boolean {
  return typeof url === "string" && /\.pdf(\?|#|$)/i.test(url);
}

function titleFromUrl(url: string | null): string | null {
  if (!url) return null;

  const file = url.split("?")[0].split("#")[0].split("/").filter(Boolean).pop();
  if (!file) return null;

  let name: string;
  try {
    name = decodeURIComponent(file);
  } catch {
    name = file;
  }

  name = name
    .replace(/\.pdf$/i, "")
    .replace(/[-_]+/g, " ")
    // A leading ordinal ("1 Courses Intake") is a filename artefact, not part
    // of the document's name.
    .replace(/^\d+[\s.)-]*/, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!name) return null;
  return `${name} (PDF)`;
}
