"use client";

import { useRouter } from "next/navigation";

export function SignOutButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={async () => {
        await fetch("/api/admin/session", { method: "DELETE" });
        router.replace("/admin/login");
        router.refresh();
      }}
      className="rounded-md border border-line bg-white px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-navy-200 hover:text-ink"
    >
      Sign out
    </button>
  );
}
