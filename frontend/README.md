# Portal frontend (`frontend/`)

Empty in Phase 0. Scaffolded in Phase 7.

Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui, per
architecture-plan.md sections 3.1 and 5.

Not started yet because the portal is only worth building once there is a real
corpus and a working pipeline behind it. Building the UI first would mean
designing pages around imagined data.

## Design direction

pce.ac.in is the **data** source, not the design source. The portal must not
look like a clone of it. Distinct typography, distinct colour system, modern
layout — a system that could plausibly be a university's next portal, not a
copy of its current one.

## Pages

Public: `/`, `/about`, `/academics`, `/departments`, `/faculty`, `/admissions`,
`/students`, `/placements`, `/research`, `/library`, `/events`, `/contact`

AI: `/ask` (chat with streaming, inline citations, source panel, reasoning
drawer), `/knowledge` (corpus explorer with chunk-boundary visualisation),
`/compare` (baseline vs proposed, side by side)

Admin: `/admin` (ingestion, corpus, content, analytics, evaluation centre)
