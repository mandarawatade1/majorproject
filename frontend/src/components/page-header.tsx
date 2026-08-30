import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow?: string;
  title: string;
  lede?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="border-b border-line bg-white">
      <div className="container-page py-10 sm:py-14">
        {eyebrow ? <p className="eyebrow mb-3">{eyebrow}</p> : null}
        <h1 className="font-serif text-title text-ink">{title}</h1>
        {lede ? <div className="mt-4 max-w-prose text-[17px] leading-relaxed text-ink-soft">{lede}</div> : null}
        {children ? <div className="mt-6">{children}</div> : null}
      </div>
    </header>
  );
}
