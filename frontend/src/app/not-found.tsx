import Link from "next/link";

export default function NotFound() {
  return (
    <div className="container-page py-24 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-3 font-serif text-title text-ink">That page isn&rsquo;t here.</h1>
      <p className="mx-auto mt-4 max-w-prose text-ink-soft">
        The link may be out of date, or the record may have left the knowledge base when the
        corpus was last rebuilt.
      </p>
      <Link
        href="/"
        className="mt-8 inline-block rounded-md bg-navy-900 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-navy-700"
      >
        Back to the portal
      </Link>
    </div>
  );
}
