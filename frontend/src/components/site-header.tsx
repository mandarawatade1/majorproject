"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/departments", label: "Departments" },
  { href: "/programs", label: "Programmes" },
  { href: "/faculty", label: "Faculty" },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/85 backdrop-blur">
      {/* min-h rather than a fixed height, because a fixed bar clips anything
          that wraps — and at 390px the full institute name wrapped to three
          lines and lost the first one off the top of the screen. */}
      <div className="container-page flex min-h-[72px] items-center justify-between gap-4 py-3 sm:gap-6">
        <Link href="/" aria-label="Pillai College of Engineering Knowledge Portal" className="flex items-center gap-3">
          <span
            aria-hidden
            className="grid h-10 w-10 shrink-0 place-items-center rounded bg-navy-900 font-serif text-lg font-bold text-white"
          >
            P
          </span>
          {/* Two variants rather than one that truncates: an abbreviation is
              read as a name, whereas "Pillai College of Engi…" reads as a bug.
              The link carries the full name as its accessible label either way. */}
          <span aria-hidden className="leading-tight">
            <span className="block font-serif text-[16px] font-semibold text-ink sm:text-[17px]">
              <span className="sm:hidden">PCE</span>
              <span className="hidden sm:inline">Pillai College of Engineering</span>
            </span>
            {/* Dropped on the narrowest screens: beside "PCE" it wrapped to
                two lines and made the wordmark look broken. The page title
                and the nav already say where you are. */}
            <span className="hidden text-[10px] uppercase tracking-[0.12em] text-ink-muted sm:block sm:text-[11px]">
              Knowledge Portal
            </span>
          </span>
        </Link>

        <nav aria-label="Primary" className="flex items-center gap-0.5 sm:gap-1">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded px-2 py-2 text-[13px] font-medium transition-colors sm:px-3 sm:text-sm ${
                  active ? "bg-navy-100 text-navy-700" : "text-ink-soft hover:bg-navy-50 hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
