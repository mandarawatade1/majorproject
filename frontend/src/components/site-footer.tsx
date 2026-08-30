import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-line bg-white">
      <div className="container-page grid gap-10 py-12 sm:grid-cols-[2fr_1fr]">
        <div>
          <p className="font-serif text-lg font-semibold text-ink">
            Pillai College of Engineering — Knowledge Portal
          </p>
          {/* Stated on every page of the site, not buried in an About box.
              A portal that mixes real institutional content with synthetic
              records and does not say so is misleading, however well the
              individual records are labelled. */}
          <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-soft">
            This portal is a final-year academic project. Its content is drawn from
            publicly available pages on pce.ac.in. A small proportion of records are
            synthetic, authored where no public source existed, and every one of them
            is marked <span className="font-medium text-gold">Demo data</span> wherever
            it appears. It is not an official publication of the college.
          </p>
        </div>

        <nav aria-label="Footer">
          <p className="eyebrow mb-3">Browse</p>
          <ul className="space-y-2 text-sm">
            <li>
              <Link href="/ask" className="text-ink-soft link-underline">
                Ask PCE
              </Link>
            </li>
            <li>
              <Link href="/departments" className="text-ink-soft link-underline">
                Departments
              </Link>
            </li>
            <li>
              <Link href="/programs" className="text-ink-soft link-underline">
                Programmes
              </Link>
            </li>
            <li>
              <Link href="/faculty" className="text-ink-soft link-underline">
                Faculty
              </Link>
            </li>
            <li>
              <Link href="/explore" className="text-ink-soft link-underline">
                Knowledge base
              </Link>
            </li>
            <li>
              <Link href="/compare" className="text-ink-soft link-underline">
                Baseline vs proposed
              </Link>
            </li>
            <li>
              <a
                href="https://www.pce.ac.in"
                className="text-ink-soft link-underline"
                rel="noreferrer noopener"
                target="_blank"
              >
                Official college website
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
