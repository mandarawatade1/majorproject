# Portal frontend — Phase 7

Next.js 14 (App Router) + TypeScript + Tailwind. Public pages only; the Ask PCE
assistant and the admin console are Phases 8 and 9.

## Running it

The backend must be up first — the portal renders on the server and fetches
from FastAPI during the render, so a page load with the stack down shows an
error panel rather than content.

```bash
docker compose up -d          # from the repository root
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                   # http://localhost:3000
```

`http://localhost:3000` is already in the backend's `CORS_ORIGINS`, though the
portal's own requests are server-to-server and never hit CORS.

## Pages

| Route | API endpoint |
| --- | --- |
| `/` | `/api/v1/departments`, `/api/v1/corpus/stats` |
| `/departments` | `/api/v1/departments` |
| `/departments/[slug]` | `/api/v1/departments/{slug}` |
| `/programs` | `/api/v1/programs?level=` |
| `/faculty` | `/api/v1/corpus/documents?category=faculty` |

Note there is no `/portal` segment: the portal router is registered with
`APIRouter(tags=["portal"])` and no prefix of its own, so its routes sit
directly under `/api/v1`.

## Two things that are deliberate

**Faculty comes from the corpus, not a `faculty` table.** The table exists in
the schema and nothing populates it. Rather than ship an empty page, `/faculty`
lists the crawled faculty pages and links each to its source, and says on the
page that this is what it is doing.

**Every demo record is labelled.** `is_demo` travels from the parser through
the manifest, the database and the API; `DemoBadge` is where that chain
terminates. Any record rendered with `is_demo: true` carries a visible,
text-based badge — not a colour alone, which a screen reader cannot announce.

## Checks

```bash
npm run typecheck
npm run lint
npm run build
```
