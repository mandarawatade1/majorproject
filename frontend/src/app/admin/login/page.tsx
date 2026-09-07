import { redirect } from "next/navigation";
import type { Metadata } from "next";

import { SignInForm } from "@/components/admin/sign-in-form";
import { isSignedIn } from "@/lib/admin";

export const metadata: Metadata = { title: "Administrator sign-in", robots: { index: false } };

export default function AdminLoginPage() {
  if (isSignedIn()) redirect("/admin");

  return (
    <div className="container-page max-w-md py-20">
      <p className="eyebrow mb-3">Administration</p>
      <h1 className="font-serif text-title text-ink">Sign in</h1>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        The portal and the assistant are public. This console is not — it reports what the
        knowledge base contains and can rebuild the index.
      </p>
      <SignInForm />
    </div>
  );
}
