"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="container-page py-24 text-center">
      <p className="eyebrow">Something broke</p>
      <h1 className="mt-3 font-serif text-title text-ink">This page couldn&rsquo;t be rendered.</h1>
      <p className="mx-auto mt-4 max-w-prose text-ink-soft">
        If the backend was starting up, it may work on a second attempt.
      </p>
      <button
        onClick={reset}
        className="mt-8 rounded-md bg-navy-900 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-navy-700"
      >
        Try again
      </button>
    </div>
  );
}
