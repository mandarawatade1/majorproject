# Demo corpus — synthetic institutional data

**Nothing in this folder is real.** Every document here is invented for the
purpose of exercising the RAG pipeline against the kind of internal material
the project targets — internal wikis, SOPs, circulars, lab manuals, helpdesk
articles — which no institution publishes on its website.

**Sizing.** The corpus rule is a floor on real data — at least 80% of
documents must be real — not a quota of synthetic data. This folder is sized by
what the evaluation needs rather than by a percentage: enough coverage across
all six internal-only categories to support a meaningful slice of the golden
set. At 39 documents and 313 sections it supports roughly 20-25 internal
questions in a 100-150 question set.

Do not add documents here to move a ratio. Add them when a category is too
thin to ask good questions of.

## Rules — these are enforced, not aspirational

1. Every file carries the front-matter block below. The loader **rejects any
   file in this folder without it**.
2. Everything ingested from here is stored with `is_demo = true` in
   `documents`, and that flag propagates to `chunks` and then to every
   citation returned by the API.
3. The UI renders an amber **DEMO DATA** badge on any citation sourced from
   here, and the chat shows a banner when a demo source contributed.
4. Identifiers are obviously synthetic: `DEMO/CE/2026/07`, never a plausible
   real circular number.
5. Never invent figures that a reader could mistake for real institutional
   fact — fee amounts, placement statistics, individual names, contact
   details, results. Where a category needs an example, make it visibly
   illustrative.

## Required front matter

```yaml
---
title: "Example internal circular"
doc_id: "DEMO/CE/2026/07"
is_demo: true
demo_reason: "Internal circulars are not published publicly; synthesised to
              exercise the ingestion path for internal documents."
category: "circular"          # circular | sop | wiki | manual | helpdesk | timetable
department: "Computer Engineering"
created: "2026-08-28"
---
```

## Why demo data exists at all

Report section 3.2.3 and survey section V scope the corpus to "internal
documents, manuals, policies, SOPs, internal wikis". That material is real in
the sense that it exists at every institution — it is simply not public. The
honest way to build and evaluate against it is to synthesise it and label it
unmistakably, which is what this folder does.
