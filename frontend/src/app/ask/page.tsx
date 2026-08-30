import type { Metadata } from "next";

import { AskPce } from "@/components/ask/ask-pce";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Ask PCE",
  description:
    "Ask a question about Pillai College of Engineering and get an answer with every claim traceable to the page it came from.",
};

export default function AskPage() {
  return (
    <>
      <PageHeader
        eyebrow="Assistant"
        title="Ask PCE"
        lede={
          <>
            Answers are generated only from documents published by the college, and every
            one carries the passages it was built from. Nothing here is answered from the
            model&rsquo;s own memory.
          </>
        }
      />
      {/* On this hardware an answer takes roughly 15 seconds under Standard and
          can take several minutes under Verified, most of it before the first
          word exists. The stage list beside the answer is not decoration; it is
          what makes that wait legible. */}
      <AskPce />
    </>
  );
}
