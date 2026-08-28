# Architecture & Implementation Plan
## AI-Based Institute Knowledge Management Using Open-Source LLM and RAG Framework

**Project:** Major Project (B.Tech Computer Engineering), Pillai College of Engineering, New Panvel — University of Mumbai, AY 2025–26
**Team:** Bhavesh Patil (B542), Arpit Bolade (B509), Soham Mali (B528), Mandar Awatade (B505)
**Supervisor:** Prof. Radhika Fulzele
**Document status:** Phase 1 deliverable — analysis and plan only. No code written. Awaiting approval.
**Date:** 28 August 2026

---

## 0. What I read, and what I found in the workspace

### 0.1 Repository inspection

Current state of `~/Documents/GitHub/majorproject2026`:

```
majorproject2026/
├── .git/              (initialised, no commits — objects/pack empty, FETCH_HEAD 0 bytes)
├── .DS_Store
└── Docs/
    ├── Report final (1).docx     (10.99 MB)
    └── survey paper (1).pdf      (1.21 MB, 12 pages)
```

**Findings:** the repo is empty apart from the two source documents. There is no existing application code, no `package.json`, no Python project, no prior scaffold. **Nothing has been deleted or modified.** Note the folder is `Docs/` (capital D), not `docs/` — this plan is being saved as `Docs/architecture-plan.md` to sit alongside your source material rather than creating a second, near-identically-named folder. Say the word if you want it renamed to lowercase.

> ⚠️ The `Docs/` folder is currently tracked in a git repo with no `.gitignore`. The `.docx` is 11 MB. Before we start committing, we should add a `.gitignore` (venv, `node_modules`, `.env`, model weights, Chroma index, scraped corpus) and consider Git LFS for the large binaries. This is a Phase 0 item.

### 0.2 Source documents — extracted terminology and technical direction

Both documents describe the **same** system and are internally consistent. The architecture below is derived from them, not invented. Key commitments I am treating as **fixed requirements**:

| From the documents | Where |
|---|---|
| Open-source LLMs, on-premise, **no proprietary cloud AI** (data sovereignty is the stated core motivation) | Report §1.1, §2.4 (Gap 1), §3.1; Survey §IV |
| **Structure-aware semantic chunking** preserving document hierarchy (sections/subsections), with low-information content filtering | Report Abstract, §2.3, §3.1.2; Survey §IV, §V |
| **Metadata enrichment**: section context, page-level provenance, headings, keywords, document references | Report Abstract, §3.1.2; Survey §IV, §V.3 |
| **Hybrid retrieval**: dense embeddings + keyword (BM25) filtering + **cross-encoder reranking** | Report §2.3, §3.1.2, §3.2.1; Survey §IV |
| Embeddings via **Sentence-BERT / transformer models**, cosine similarity, **FAISS or Chroma** vector DB | Report §3.2.1, Table 3.2 |
| **Agentic planner–executor layer**: multi-step query decomposition, iterative retrieval, failure-aware refinement; Chain-of-Thought / **ReAct** techniques | Report Abstract, §1.2, §3.1.2, §3.2.1; Survey §IV |
| **Citation-backed generation** with page-level provenance; refusal/grounding enforcement | Report Abstract, §2.4 (Gap 4), §3.1.2 |
| **Post-answer verification** against retrieved context to catch hallucination | Report Abstract, §3.1.2; Survey §IV |
| Evaluation via **RAGAS** — Faithfulness, Answer Relevancy, Context Precision — plus **LLM-as-a-judge** | Report §3.3; Survey §VI |
| Comparison against a **conventional/naive RAG baseline** ("improved … compared to conventional RAG baselines") | Report Abstract, §3.1.1 |
| Implementation stack named: **LangChain, LangGraph, Ollama, Streamlit**, Python | Survey §IV; Report Table 3.2 |
| Corpus: institutional PDFs, reports, manuals, policies, SOPs, internal wikis, technical documentation | Report §3.2.3; Survey §V.1 |
| Hardware baseline: Intel i5 / Ryzen 5, **8 GB RAM**, 512 GB SSD (the "5112" in Table 3.1 appears to be a typo for 512 GB) | Report Table 3.1 |

**Research gaps the system must visibly close** (Report §2.4) — these become our demo talking points and our evaluation axes: (1) data sovereignty, (2) loss of document hierarchy, (3) limited multi-hop reasoning/autonomy, (4) inadequate grounding and explainability, (5) manual/subjective evaluation.

### 0.3 Two deviations from the documents I am proposing — these need your explicit approval

**Deviation A — the UI layer.** The survey paper names **Streamlit** for the interface. Streamlit cannot produce "a modern production-level university portal": it has no routing, no design system, no role-based page structure, and everything renders as a single reactive script. Your instruction ("do NOT create a simple static college website … should look like a modern production-level university portal") is incompatible with it.

**Proposal:** keep the RAG core exactly as documented (LangChain + LangGraph + Ollama + Chroma), and change **only the presentation layer** to Next.js + FastAPI. Streamlit is retained for one thing it is genuinely good at: an internal **evaluation/experiment console** for the RAGAS runs and ablation charts you need for Chapter 4. That way the report stays truthful — Streamlit is still in the stack, just scoped to the research tooling. We add a sentence to §3.2 of the report explaining the interface upgrade.

**Deviation B — the vector store.** Report Table 3.2 says "FAISS/Chroma". I recommend **Chroma** (not FAISS) because we need per-chunk metadata filtering (department, doc type, date, `is_demo`) for hybrid retrieval, which FAISS does not do natively. Chroma is explicitly listed as an accepted option in your own table, so this is a selection, not a deviation. FAISS remains available behind an interface if you want a speed comparison for the report.

---

## 1. Project architecture

### 1.1 High-level shape

Four services, each independently runnable, all open-source, all local:

```
┌───────────────────────────────────────────────────────────────────────┐
│  1. WEB PORTAL          Next.js 14 (App Router) + TypeScript          │
│     Public pages · Ask PCE chat · Admin console                        │
└───────────────┬───────────────────────────────────────────────────────┘
                │  REST + SSE (streaming tokens & citations)
┌───────────────▼───────────────────────────────────────────────────────┐
│  2. API / APPLICATION LAYER        FastAPI (Python 3.11)              │
│     Auth (JWT) · RBAC · Portal CRUD · Chat orchestration · Admin API   │
└──────┬─────────────────────────────────────────┬──────────────────────┘
       │                                          │
┌──────▼──────────────────┐          ┌────────────▼──────────────────────┐
│ 3. KNOWLEDGE SERVICE     │          │ 4. DATA LAYER                     │
│  ┌────────────────────┐  │          │  PostgreSQL 16  (relational)      │
│  │ Ingestion pipeline │  │          │  Chroma         (dense vectors)   │
│  │ crawl→parse→chunk  │  │          │  BM25 index     (sparse, on disk) │
│  │ →enrich→embed      │  │          │  Redis          (cache, job queue)│
│  ├────────────────────┤  │          │  ./corpus/      (raw + normalised)│
│  │ Retrieval engine   │  │          └───────────────────────────────────┘
│  │ dense+BM25+RRF     │  │
│  │ +cross-encoder RR  │  │          ┌───────────────────────────────────┐
│  ├────────────────────┤  │◄────────►│  OLLAMA  (local model runtime)    │
│  │ Agentic layer      │  │          │  generator LLM · judge LLM        │
│  │ LangGraph P→E→V    │  │          │  embedding model                  │
│  ├────────────────────┤  │          └───────────────────────────────────┘
│  │ Verification layer │  │
│  └────────────────────┘  │          ┌───────────────────────────────────┐
└──────────────────────────┘          │  EVAL CONSOLE (Streamlit)         │
                                      │  RAGAS · LLM-judge · ablations    │
                                      └───────────────────────────────────┘
```

### 1.2 Why this separation matters for your viva

The knowledge service is a **library plus a thin service**, not glue code inside the web app. That means:

- The **baseline naive RAG** (Report §3.1.1) and the **proposed pipeline** (§3.1.2) are two configurations of the same interface, swappable by a config flag. Your Chapter 4 comparison is then a fair, single-variable comparison instead of two different programs.
- Each innovation (structure-aware chunking, hybrid retrieval, reranking, agentic layer, verification) is a **toggleable stage**, so we can run proper **ablation studies** — "hybrid retrieval alone gives +X context precision; adding rerank gives +Y" — which is exactly the kind of result table that lifts a major project report.
- Nothing leaves the machine. Ollama, Chroma, and Postgres all run locally, which is the literal demonstration of research gap #1.

### 1.3 Request flow for a question

```
User: "What is the intake for Computer Engineering and is the programme NBA accredited?"
  │
  ├─► API: auth, rate-limit, load chat session, persist user message
  ├─► Agentic layer (LangGraph):
  │     PLANNER   → decomposes into 2 sub-questions + picks tools
  │     EXECUTOR  → sub-q1: kb_search(filter: doc_type=programs)
  │                 sub-q2: kb_search(filter: doc_type=accreditation)
  │                   each: dense(k=20) ∥ BM25(k=20) → RRF → rerank → top-5
  │                          → parent-chunk expansion
  │     CRITIC    → "is the retrieved context sufficient for each sub-q?"
  │                  if no → rewrite query, retry (max 3 loops)
  │     SYNTHESIS → grounded generation with [S1][S2] citation markers
  │
  ├─► VERIFIER: extract atomic claims → entailment-check each against its
  │              cited chunk → mark supported / unsupported → strip or flag
  │
  └─► Response streamed to UI: answer + inline citations + source panel
      (doc title, section path, page number, deep link, REAL/DEMO badge)
      + confidence indicator + "log for evaluation" hook
```

---

## 2. Data sources — what is real, what is demo, and why

### 2.1 Findings from inspecting pce.ac.in

I was able to browse the live site. Its public information architecture has **13 top-level sections**: Home, About, Academics, Students, Faculty, Research, Library, Alumni, NBA–DCS, IQAC, Accreditation, Events, Extension. There is also a separate admissions subdomain (`admissions.pce.ac.in`) with a public FAQ.

Concrete, verifiable facts already confirmed (a sample of what we can ingest):

- Established **1999**; courses commenced AY 2000–01; trust is **Mahatma Education Society** (founded 1970); formerly PIIT, renamed PCE in **2016**
- Affiliated to **University of Mumbai**; AICTE approved; UGC 2(f) and 12(B) since **2015**; **autonomous since AY 2021–22**
- **NAAC A+**; NBA accreditation for 6 UG programmes (2008, re-accredited 2015, 2018, 2022)
- Campus: Dr. K.M. Vasudevan Pillai Campus, New Panvel — **16 acres, 2,30,000 sq ft, 2,700+ students**
- **6 B.Tech programmes, total sanctioned intake 630**, with DTE choice codes and start years:

| Programme | Choice code | Intake | Since |
|---|---|---|---|
| Computer Engineering | 320724510 | 180 | 1999 |
| Information Technology | 320724610 | 120 | 1999 |
| Electronics & Telecommunication | 320737210 | 120 | 2007 |
| Electronics & Computer Science | 320790010 | 90 | 1999 |
| Automobile Engineering | 320760210 | 60 | 2009 |
| Mechanical Engineering | 320761210 | 60 | 2002 |

- 4 M.Tech specialisations, 3 PhD research centres
- **Admission notice 2026–27:** the college is *not* participating in State CET Cell CAP counselling rounds; applicants apply to Pillai University directly — a genuinely useful, time-sensitive fact for the assistant to answer
- Public PDFs suitable as a RAG corpus: **Annual Reports** (e.g. AY 2023–24), NIRF submissions (Overall / Engineering / Innovation), NAAC documents, IQAC reports and audits, mandatory disclosures, curriculum & syllabus pages per department, student and faculty handbooks, academic calendar

### 2.2 The 80/20 split

**REAL (~80% of corpus) — scraped or downloaded from public PCE sources**

| Category | Source | Format |
|---|---|---|
| Institute profile, history, vision, mission | `/about/the-institute/` | HTML |
| Leadership, governance, org structure | `/about/*` | HTML |
| Accreditation: NAAC, NBA, NIRF, ARIIA | `/accreditation/*` | HTML + PDF |
| 6 B.Tech + 4 M.Tech + PhD programme details, intake, choice codes | `/academics/bachelors/`, `/masters/` | HTML |
| Curriculum & syllabus per department | `/bachelors/<dept>/curriculum/` | HTML + PDF |
| Faculty directory & profiles | `/faculty/*` | HTML |
| Research areas, facilities, publications, MOUs | `/research/*` | HTML + PDF |
| Library information, resources, statistics | `/library/*` | HTML |
| Student activities, associations, councils, handbooks | `/students/*` | HTML + PDF |
| Placements & internships information | `/students/placements` | HTML |
| Announcements, notices, events, news | homepage + `/events/*` | HTML |
| Admission process & FAQ | `admissions.pce.ac.in` | HTML |
| Annual reports, IQAC reports, mandatory disclosures | site PDFs | PDF |
| Contact details, campus addresses | footer + `/about/contact` | HTML |

**DEMO (~20% of corpus) — synthesised, clearly labelled, never presented as real**

| Category | Why it must be demo |
|---|---|
| Individual student records, marksheets, attendance | Personal data; behind login; illegal to scrape and wrong to fabricate as real |
| Student/faculty portal logins & session data | Authenticated area; not public |
| Division-wise timetables, exam seat allocation | Not published openly |
| Internal circulars, SOPs, office memoranda | The report explicitly targets "internal wikis, SOPs, policies" — no institution publishes these, so we must synthesise a plausible internal-wiki set to exercise the pipeline |
| Hostel/mess rules and current fee amounts | Fee figures change and are quoted through the admission portal; publishing a stale figure in a demo would be misinformation |
| IT helpdesk tickets / knowledge base articles | Internal system, not public |
| Departmental lab manuals with step-by-step procedures | Distributed to students, not on the public site |
| A small set of faculty office hours & mentor allocations | Semester-specific internal data |

**How demo data is kept honest — this is a design requirement, not a footnote:**

1. Every document row carries `is_demo BOOLEAN NOT NULL`. It is a column, not a naming convention.
2. Demo source files live in a physically separate `corpus/demo/` tree with a mandatory `DEMO-DATA.md` header block inside each file.
3. The chunk metadata inherits `is_demo`, so it survives all the way through retrieval into the citation object.
4. The UI renders an amber **"DEMO DATA"** badge on every citation sourced from a demo document, and the chat shows a banner when any demo source contributed to an answer.
5. The admin console shows a live real/demo ratio so we can prove the 80/20 target during the demo.
6. Synthetic content is written to be *plausible but obviously not authoritative* — e.g. "Circular No. DEMO/CE/2026/07".

### 2.3 Scraping ethics and legality — worth a paragraph in the report

We are ingesting a real institution's public website. The crawler will: obey `robots.txt`; use a descriptive User-Agent identifying it as an academic project; rate-limit to ~1 request/second with backoff; crawl only `pce.ac.in` and `admissions.pce.ac.in`; cache locally so we crawl once, not on every run; and retain the source URL and fetch timestamp for every document so all content is attributed. The corpus is used for academic evaluation, not redistribution. I recommend a one-line mention to your supervisor, and ideally an informal heads-up to the IT/webmaster team — that is also a nice line in the report's "ethical considerations".

---

## 3. Tech stack

Everything below is open-source and runs locally. **No paid APIs anywhere in the pipeline**, including evaluation (the LLM-as-a-judge runs on Ollama too — many teams accidentally break the "no proprietary AI" claim right at the evaluation step, and examiners notice).

### 3.1 Frontend
| Concern | Choice | Rationale |
|---|---|---|
| Framework | **Next.js 14** (App Router) + **TypeScript** | Server components for fast public pages, real routing for a portal-shaped IA, one deployable |
| Styling | **Tailwind CSS** + **shadcn/ui** (Radix) | Production-grade component primitives, accessible by default, no design-by-accident |
| State/data | TanStack Query + Zustand | Server cache vs UI state kept separate |
| Streaming chat | Server-Sent Events (`fetch` + `ReadableStream`) | Token-by-token answers; citations pushed as structured events |
| Charts | Recharts | Admin analytics + RAGAS result visualisations |
| Icons/type | lucide-react; Inter + a serif display face | Distinct visual identity — deliberately *not* a pce.ac.in clone |

### 3.2 Backend
| Concern | Choice | Rationale |
|---|---|---|
| API | **FastAPI** + Uvicorn, Python 3.11 | Same language as the RAG stack, async, auto OpenAPI docs (good report appendix) |
| ORM / migrations | SQLAlchemy 2.0 + **Alembic** | Versioned schema — reviewable per phase |
| Validation | Pydantic v2 | Typed contracts shared with the RAG layer |
| Auth | JWT (access + refresh), `passlib[bcrypt]`, RBAC | Roles: `guest`, `student`, `faculty`, `admin` |
| Background jobs | Celery + Redis (fallback: FastAPI BackgroundTasks) | Ingestion and eval runs are long; must not block requests |
| Testing | pytest + httpx + testcontainers | Phase gates need real tests, not vibes |

### 3.3 AI / RAG stack — the core
| Concern | Choice | Rationale |
|---|---|---|
| LLM runtime | **Ollama** | Named in your survey paper; simplest fully-local serving |
| Generator LLM | **`qwen2.5:7b-instruct-q4_K_M`** (primary) or `llama3.1:8b-instruct-q4_K_M` | Strong instruction-following and citation discipline at 7–8B; ~5 GB quantised |
| Small-hardware fallback | `qwen2.5:3b-instruct` / `llama3.2:3b` | For the 8 GB machine in Report Table 3.1 — see §3.6 |
| Judge LLM | A **different** local model (e.g. `llama3.1:8b` if generator is Qwen) | Self-judging inflates scores; using a different family is defensible methodology |
| Embeddings | **`BAAI/bge-small-en-v1.5`** (384-d) via sentence-transformers | Sentence-BERT family as your report specifies; fast on CPU; strong MTEB retrieval scores. Upgrade path: `bge-base-en-v1.5` (768-d) |
| Reranker | **`BAAI/bge-reranker-base`** cross-encoder | The "cross-encoder reranking" your report §3.2.1 names |
| Vector DB | **ChromaDB** (persistent, HNSW) | Metadata filtering + hybrid support; listed in your Table 3.2 |
| Sparse retrieval | **BM25** via `rank_bm25` (or Postgres FTS for scale) | The keyword half of hybrid retrieval |
| Fusion | **Reciprocal Rank Fusion (RRF)** | Score-scale-agnostic; the standard defensible fusion method |
| Orchestration | **LangChain** (loaders, splitters, interfaces) | Named in your survey paper |
| Agent framework | **LangGraph** (stateful graph, cycles, checkpointing) | Named in your survey paper; cycles are what make planner→executor→critic loops possible |
| PDF parsing | **PyMuPDF** (fast, page-accurate) + `pdfplumber` (tables) + `unstructured` (fallback) | Page-level provenance is a hard requirement; PyMuPDF gives exact page numbers |
| HTML parsing | httpx + selectolax/BeautifulSoup + `trafilatura` | `trafilatura` strips nav/footer boilerplate — directly implements the "low-information content filtering" in your abstract |
| Evaluation | **RAGAS** + custom LLM-judge rubric | Faithfulness, Answer Relevancy, Context Precision, Context Recall |
| Eval console | **Streamlit** | Keeps Streamlit in the stack, scoped to research tooling |

### 3.4 Data layer
- **PostgreSQL 16** — institutional entities, users, chats, citations, eval results, audit logs
- **ChromaDB** — dense vectors, persisted to disk under `./data/chroma`
- **BM25 index** — pickled sparse index rebuilt on ingest, under `./data/bm25`
- **Redis** — response cache, embedding cache, Celery broker
- **`./corpus/`** — `raw/` (as-fetched), `normalised/` (markdown + JSON sidecars), `demo/` (labelled synthetic)

> Optional simplification: **pgvector** instead of Chroma collapses the vector store into Postgres (one fewer moving part, SQL-native metadata filters). Chroma is closer to your report's Table 3.2, so it's the default — flagging it as a decision point.

### 3.5 DevOps
Docker Compose (postgres, redis, chroma, api, web, ollama) · `.env` config with Pydantic Settings · ruff + black + mypy · ESLint + Prettier · GitHub Actions for lint+test · structured JSON logging with a per-request trace ID that follows a query through every RAG stage (invaluable for the report's pipeline walkthrough figure).

### 3.6 A hardware reality check — please read this one

Report Table 3.1 specifies **8 GB RAM**. That is workable but tight, and I'd rather flag it now than have it bite during the demo:

| Component | RAM at rest |
|---|---|
| 7–8B generator LLM, Q4 quantised | ~5.0–5.5 GB |
| bge-small embedding model | ~0.15 GB |
| bge-reranker-base cross-encoder | ~0.5 GB |
| Postgres + Redis + Chroma | ~1.0 GB |
| FastAPI + Next.js dev server | ~1.0 GB |
| **Total** | **~8+ GB — over budget on an 8 GB machine** |

Three options: **(a)** develop on 16 GB (ideal — 7B model, everything comfortable); **(b)** run on 8 GB with a 3B generator and lazy-load the reranker (works, quality drops a little, demo is safe); **(c)** run Ollama on one machine on the college LAN and point the API at it. Recommendation: **(a) if any team member has 16 GB, else (b)**, and we mention the CPU-only inference latency honestly in the report's limitations section. If anyone has an NVIDIA GPU or an Apple Silicon Mac, that machine should be the demo machine.

---

## 4. Database schema

PostgreSQL. Grouped into four domains. `is_demo` propagates from source through to citation — that is the mechanism that makes the 80/20 labelling trustworthy rather than cosmetic.

### 4.1 Institutional domain (powers the portal pages)

```sql
departments        (id, code, name, slug, established_year, hod_name, about,
                    vision, mission, email, phone, is_demo, created_at, updated_at)

programs           (id, department_id→departments, level ENUM(btech,mtech,phd),
                    name, choice_code, intake, duration_years, started_year,
                    description, curriculum_url, is_demo)

courses            (id, program_id→programs, code, title, semester, credits,
                    course_type, syllabus_url, outcomes JSONB, is_demo)

faculty            (id, department_id→departments, name, designation,
                    qualification, specialisation, email, experience_years,
                    profile_url, photo_url, publications_count, is_demo)

announcements      (id, title, body, category ENUM(notice,circular,result,
                    admission,event), published_at, expires_at, priority,
                    attachment_url, source_url, is_demo)

events             (id, title, description, starts_at, ends_at, venue,
                    organiser, category, banner_url, source_url, is_demo)

facilities         (id, name, category ENUM(lab,library,sports,hostel,
                    infrastructure), description, department_id, is_demo)

placements         (id, academic_year, company_name, students_placed,
                    highest_package, average_package, department_id, is_demo)

accreditations     (id, body ENUM(naac,nba,nirf,ariia,ugc,aicte), grade,
                    scope, valid_from, valid_to, certificate_url, is_demo)

contacts           (id, label, department_id, phone, email, address, category)
```

### 4.2 Knowledge / RAG domain (the heart of the system)

```sql
documents          (id, title, source_type ENUM(web,pdf,docx,manual_entry),
                    source_url, local_path, doc_category, department_id,
                    author, published_date, fetched_at, content_hash,
                    page_count, language, is_demo, ingest_status,
                    ingest_error, version, created_at)
                   -- content_hash enables change detection & re-ingest

document_sections  (id, document_id→documents, parent_section_id→self,
                    heading, level, section_path TEXT, order_index,
                    start_page, end_page)
                   -- the explicit hierarchy tree = "structure-aware"

chunks             (id, document_id→documents, section_id→document_sections,
                    parent_chunk_id→self, chunk_index, content TEXT,
                    content_summary TEXT, hypothetical_questions TEXT[],
                    token_count, page_number, section_path, char_start,
                    char_end, embedding_model, is_demo, metadata JSONB)
                   -- parent_chunk_id gives small-to-big retrieval
                   -- page_number gives page-level provenance (Gap 4)

chunk_vectors      -- lives in Chroma, keyed by chunks.id; Postgres holds the
                   -- source of truth, Chroma the ANN index
```

### 4.3 Conversation, citation and evaluation domain

```sql
users              (id, email, password_hash, full_name, role ENUM(guest,
                    student,faculty,admin), department_id, is_active,
                    last_login_at, created_at)

chat_sessions      (id, user_id→users NULLABLE, title, mode ENUM(baseline,
                    proposed), created_at, last_message_at)

chat_messages      (id, session_id→chat_sessions, role ENUM(user,assistant,
                    system), content TEXT, reasoning_trace JSONB,
                    latency_ms, token_count, model_name, confidence_score,
                    verification_status ENUM(verified,partial,unverified),
                    created_at)
                   -- reasoning_trace stores the LangGraph plan/steps for the
                   -- "show your working" panel — this is the explainability win

message_citations  (id, message_id→chat_messages, chunk_id→chunks,
                    marker TEXT, relevance_score, rerank_score,
                    quoted_span TEXT, is_demo)

retrieval_logs     (id, message_id→chat_messages, original_query,
                    rewritten_queries TEXT[], sub_questions TEXT[],
                    dense_hits JSONB, sparse_hits JSONB, fused_hits JSONB,
                    reranked_hits JSONB, filters_applied JSONB,
                    stage_latencies JSONB, iteration_count)
                   -- every ablation number in Chapter 4 comes from this table

verification_results (id, message_id→chat_messages, claim TEXT,
                    supporting_chunk_id→chunks, entailment_label
                    ENUM(supported,contradicted,not_found),
                    entailment_score, action_taken)

feedback           (id, message_id→chat_messages, user_id, rating SMALLINT,
                    was_helpful BOOLEAN, comment TEXT, created_at)

eval_datasets      (id, name, description, question_count, created_at)
eval_questions     (id, dataset_id→eval_datasets, question, ground_truth,
                    question_type ENUM(factual,multi_hop,comparative,
                    unanswerable), expected_doc_ids UUID[], difficulty)
                   -- "unanswerable" questions test refusal — a strong result
eval_runs          (id, dataset_id, config_name, config JSONB, model_name,
                    started_at, finished_at, status)
eval_results       (id, run_id→eval_runs, question_id→eval_questions,
                    generated_answer, retrieved_context JSONB,
                    faithfulness, answer_relevancy, context_precision,
                    context_recall, judge_score, judge_rationale, latency_ms)

ingestion_jobs     (id, job_type, source, status, documents_processed,
                    chunks_created, started_at, finished_at, log TEXT)
audit_logs         (id, user_id, action, entity_type, entity_id,
                    ip_address, created_at)
```

**Indexes:** GIN on `chunks.metadata` and `chunks.content` (FTS/BM25 fallback); B-tree on every FK, on `documents.content_hash`, `announcements.published_at DESC`, `chat_messages.session_id`; partial index `WHERE is_demo = false` for real-only retrieval mode.

---

## 5. Page structure

### 5.1 Public portal
| Route | Content | Data source |
|---|---|---|
| `/` | Hero, quick stats (16 acres, 2700+ students, NAAC A+, 630 intake), announcements ticker, programme cards, events, **prominent "Ask PCE" entry point** | Real |
| `/about` | Institute, history (1999, MES 1970, PIIT→PCE 2016), vision, mission, leadership, campus | Real |
| `/about/accreditation` | NAAC A+, NBA cycles, NIRF, ARIIA, UGC 2(f)/12(B), certificate viewer | Real |
| `/academics` | Programme overview across B.Tech / M.Tech / PhD | Real |
| `/academics/[level]/[dept]` | Programme detail: intake, choice code, curriculum, outcomes, faculty | Real |
| `/departments` + `/departments/[slug]` | 6 department landing pages: about, HoD, labs, faculty, research, achievements | Real |
| `/faculty` | Searchable, filterable directory with profile modals | Real |
| `/admissions` | Process, eligibility, **the 2026-27 no-CAP notice**, FAQ accordion, fee structure | Real (fees marked demo if not published) |
| `/students` | Activities, associations (IEEE, CSI, NSS, racing teams), council, handbooks, calendar | Real |
| `/placements` | Statistics, recruiters, training, internships | Real + demo stats where unpublished |
| `/research` | Areas, facilities, publications, MOUs, PhD centres | Real |
| `/library` | Resources, digital collections, timings, statistics | Real |
| `/events` + `/events/[slug]` | News, notices, upcoming events, archive | Real |
| `/contact` | Departments, phone numbers, map, enquiry form | Real |

### 5.2 The AI layer — where the project actually lives
| Route | Content |
|---|---|
| `/ask` | **Ask PCE** — full-page chat. Streaming answers · inline `[1][2]` citation chips · right-hand source panel showing document title, section path, page number, quoted span, REAL/DEMO badge, deep link · confidence indicator · "Show reasoning" drawer exposing the planner's sub-questions and retrieval steps · suggested starter questions · thumbs up/down feedback |
| `/ask/[sessionId]` | Persistent conversation history |
| `/knowledge` | Knowledge base explorer: browse the corpus by department / type / date, full-text + semantic search, real-vs-demo filter, in-browser document viewer with chunk highlighting |
| `/knowledge/[docId]` | Document detail with its section tree and chunk boundaries visualised — this single page makes "structure-aware chunking" *visible* to an examiner instead of a claim |
| `/compare` | **Baseline vs Proposed** side-by-side: same question, naive RAG on the left, full pipeline on the right, with per-stage latency and retrieved-context diff. This is your best live-demo asset |

### 5.3 Admin console (`/admin`, role-gated)
Dashboard (corpus size, real/demo ratio, query volume, latency p50/p95, unanswered queries) · Ingestion manager (trigger crawl, upload PDFs, re-index, watch job logs) · Corpus manager (documents table, toggle `is_demo`, re-chunk, delete, preview) · Content manager (CRUD for announcements, events, faculty, programmes) · **Evaluation centre** (build golden sets, launch RAGAS runs, compare configs, export charts and LaTeX/CSV tables straight into your report) · Query analytics (top queries, low-confidence answers, negative feedback → corpus gaps) · Users & audit log.

### 5.4 Streamlit eval console (separate, port 8501)
Ablation runner, RAGAS metric plots, per-question drill-down, judge-rationale browser, export to PNG/CSV for Chapter 4 figures.

---

## 6. RAG pipeline — detailed design

### Stage 1 — Ingestion
Sitemap-driven polite crawler (robots.txt, 1 req/s, descriptive UA) over `pce.ac.in` + `admissions.pce.ac.in`; `trafilatura` strips nav/footer/boilerplate (this *is* the "low-information content filtering" from your abstract); HTML → markdown preserving the `h1..h6` tree. PDFs via PyMuPDF with exact page numbers per text block, `pdfplumber` for tables (rendered as markdown so the LLM can read them), OCR fallback via Tesseract for scanned pages. Each document gets a `content_hash` so re-crawls only re-process what changed. Demo documents are authored as markdown with front-matter in `corpus/demo/` and loaded through the identical path with `is_demo=true`.

### Stage 2 — Structure-aware semantic chunking (Innovation #1)
Three passes, in this order:

1. **Structural split** — walk the heading tree; each leaf section becomes a candidate unit; the full `section_path` ("Academics › B.Tech › Computer Engineering › Curriculum › Semester V") is retained. Chunks never cross a heading boundary. Tables and list blocks are kept atomic.
2. **Semantic split within section** — for sections longer than the token budget, embed sentences and split at the largest embedding-distance breakpoints (percentile thresholding) rather than at a fixed character count. Target 256–512 tokens, hard max 800, ~15% overlap at boundaries.
3. **Low-information filter** — drop chunks below a minimum character count, above a boilerplate-similarity threshold against a learned boilerplate profile, or with a stopword ratio above threshold. Every drop is logged, and the drop count becomes a reportable number.

**Small-to-big:** each chunk stores `parent_chunk_id` pointing at its full section. We *retrieve* on precise child chunks and *generate* on the expanded parent — better recall precision without starving the LLM of context.

### Stage 3 — Metadata enrichment (Innovation #1b)
Per chunk: `section_path`, `page_number`, heading hierarchy, `document_category`, `department`, `published_date`, `source_url`, `is_demo`, extracted entities (departments, programmes, people, dates, numbers), a one-line LLM-generated `content_summary`, and 2–3 LLM-generated `hypothetical_questions`. The summary and hypothetical questions are embedded alongside the raw text (a multi-representation index), which measurably improves recall for natural-language queries — and gives you a clean ablation to report.

### Stage 4 — Indexing
Dense: `bge-small-en-v1.5` (384-d, normalised) → Chroma HNSW with full metadata. Sparse: BM25 over tokenised chunk text plus section paths, persisted to disk. Both keyed by `chunks.id`, both rebuilt idempotently per ingestion job.

### Stage 5 — Hybrid retrieval (Innovation #2)
```
query
 ├─ query analysis: spell-fix, acronym expansion (CE→Computer Engineering,
 │  TE→Third Year, CAP→Centralised Admission Process), metadata-filter
 │  extraction (department? doc type? year?), multi-query rewrite (n=3)
 ├─ DENSE   : Chroma cosine top-20 (metadata-filtered)
 ├─ SPARSE  : BM25 top-20 (same filter)
 ├─ FUSION  : Reciprocal Rank Fusion, k=60  →  top-15 candidates
 ├─ RERANK  : bge-reranker-base cross-encoder scores (query, chunk) → top-5
 └─ EXPAND  : swap each child chunk for its parent section; dedupe; assemble
              context under a token budget with citation markers attached
```

### Stage 6 — Agentic planner–executor (Innovation #3, LangGraph)
A stateful graph, not a linear chain:

```
[classify] → simple? ──────────────────────────► [retrieve] → [generate]
     │
     └→ complex ─► [plan] ─► [execute sub-q] ─► [assess sufficiency]
                      ▲              │                    │
                      │              └─ more sub-qs ──────┘
                      │                                    │
                      └───── replan (max 3, on failure) ◄──┘
                                                           │
                                        [synthesise] ─► [verify] ─► [respond]
```

- **Classifier** routes simple factual lookups straight through (keeps p50 latency sane — a portal where every "what is the intake?" takes 40 seconds fails its users).
- **Planner** decomposes multi-hop and comparative questions into ordered sub-questions with per-sub-question metadata filters.
- **Executor** runs the Stage 5 pipeline per sub-question; also has tools for structured lookups (`sql_lookup` against the institutional tables for exact facts like intake numbers and event dates — an LLM should never be asked to *recall* a number a database can *return*), and a `list_documents` tool.
- **Critic** judges sufficiency of gathered context per sub-question; on failure it rewrites the query, widens filters, or raises k, then retries — this is the "failure-aware answer refinement" in your abstract. Hard cap of 3 iterations with a time budget.
- **Synthesiser** composes the final grounded answer.
- The whole plan/step trace is persisted to `chat_messages.reasoning_trace` and rendered in the "Show reasoning" drawer.

### Stage 7 — Citation-backed generation (Innovation #4)
Context blocks are injected pre-labelled `[S1] (Doc: …, Section: …, Page: 12)`. The system prompt enforces: answer **only** from context; attach `[Sn]` to every factual sentence; if the context does not contain the answer, say so and suggest where to look — never guess. Response format is constrained (Pydantic/JSON schema) so citation markers can be parsed reliably rather than regex-scraped. Post-processing maps each `[Sn]` back to a `chunk_id` and writes a `message_citations` row with the quoted span, so the UI can highlight the exact supporting sentence inside the source document.

### Stage 8 — Post-answer verification (Innovation #5)
The answer is decomposed into atomic claims. Each claim is checked for entailment against its own cited chunk — primarily a lightweight local NLI cross-encoder, with an LLM entailment prompt as fallback. Each claim gets `supported` / `contradicted` / `not_found`. Unsupported claims are either removed or visibly flagged, and the message's `verification_status` and `confidence_score` are set from the aggregate. Everything lands in `verification_results`, which gives you a hallucination-rate number to report — a much stronger claim than "we used a good prompt".

### Stage 9 — Evaluation
Golden set of **100–150 questions** spanning factual (40%), multi-hop (25%), comparative (15%), temporal (10%), and **unanswerable (10%)** — with ground truths written by your team from source documents. RAGAS computes Faithfulness, Answer Relevancy, Context Precision and Context Recall, with a local judge model. An LLM-as-a-judge rubric adds correctness, completeness, coherence, and citation quality on a 1–5 scale. Retrieval is separately scored with Hit Rate@k, MRR, and nDCG@k.

**Configurations to compare** (this table is your Chapter 4):

| # | Config | What it isolates |
|---|---|---|
| C0 | Naive RAG: fixed 512-char chunks, dense-only, top-5, no citations | The baseline of Report §3.1.1 |
| C1 | C0 + structure-aware semantic chunking | Value of Innovation #1 |
| C2 | C1 + hybrid dense+BM25 with RRF | Value of hybrid retrieval |
| C3 | C2 + cross-encoder reranking | Value of the reranker |
| C4 | C3 + agentic planner–executor | Value of Innovation #3 |
| C5 | C4 + verification layer (**full proposed system**) | Value of Innovation #5 |

Report mean ± std over 3 runs, plus latency per config so the accuracy/latency trade-off is stated honestly.

---

## 7. Implementation plan — phased, each phase gated on your approval

| Phase | Deliverable | Definition of done |
|---|---|---|
| **0. Foundations** ✅ | Repo scaffold, `.gitignore`, Git LFS, Docker Compose, `.env.example`, README, CI, Alembic init | `docker compose up` brings up postgres+redis+chroma+ollama; models pulled; health checks green — **built and statically verified; the runtime check is `./scripts/verify-stack.sh`, which must be run on the team's Mac (see §10)** |
| **1. Corpus acquisition** ◐ | Crawler, PDF/HTML parsers, corpus manifest with real/demo labels, `corpus/` populated | Code complete, 113 tests passing, pipeline run end to end; demo set authored (19 documents, 149 sections); **the crawl itself must run on the team's Mac** — see §11 |
| **2. Data layer** | Full schema + migrations + seed scripts populating departments, programmes, faculty, announcements from the corpus | All tables migrate cleanly; portal-facing data queryable; seed is reproducible from scratch |
| **3. Baseline RAG (C0)** | Naive pipeline end-to-end + CLI | Answers questions from the corpus; **this is the comparison baseline, built deliberately, not as a throwaway** |
| **4. Proposed retrieval (C1–C3)** | Structure-aware chunking, enrichment, hybrid + RRF + reranking, citation assembly | Measurable improvement over C0 on the retrieval metrics; every stage individually toggleable |
| **5. Agentic + verification (C4–C5)** | LangGraph planner–executor–critic, tool layer, claim verification | Multi-hop questions answered correctly; reasoning traces persisted; unsupported claims flagged |
| **6. Backend API** | FastAPI: auth, RBAC, portal endpoints, chat with SSE streaming, admin endpoints | OpenAPI docs complete; pytest suite green |
| **7. Portal frontend** | All public pages, design system, responsive, accessible | Lighthouse ≥90 on performance and a11y; looks like a real university portal, not a template |
| **8. Ask PCE + knowledge explorer** | Chat UI with streaming, citations, source panel, reasoning drawer; corpus browser; `/compare` page | A stranger can ask a question and trace every sentence back to a page number |
| **9. Admin console** | Ingestion, corpus, content, analytics, evaluation centre | An admin can re-crawl, re-index, and launch an eval run without touching a terminal |
| **10. Evaluation & results** | Golden set, RAGAS harness, C0–C5 ablation runs, Streamlit console, exported figures | Result tables and charts ready to paste into Chapter 4 |
| **11. Hardening & handover** | Caching, rate limits, error states, empty states, seed/demo script, deployment guide, viva demo script | Cold-start to working demo in under 15 minutes on a clean machine |

**Suggested review rhythm:** I build a phase, show you what it does, you approve or redirect, we move on. Phases 3–5 are the research core and deserve the most scrutiny; phases 7–8 are where the "production portal" judgement gets made.

---

## 8. Risks I want on the record now

| Risk | Mitigation |
|---|---|
| 8 GB RAM cannot comfortably hold a 7B model + reranker + services | §3.6 options; decide the demo machine early |
| CPU-only inference makes agentic multi-hop answers slow (20–60 s) | Complexity classifier routes simple queries around the agent; aggressive caching; state latency honestly in limitations |
| PCE site structure changes mid-project and breaks the crawler | Cache raw HTML in `corpus/raw/`; crawl once and pin; parsers tolerate missing selectors |
| Demo data gets mistaken for real during the viva | `is_demo` enforced at DB level, surfaced in every citation, banner in chat, ratio on admin dashboard |
| RAGAS itself needs an LLM and is slow locally | Run eval as a batch Celery job overnight; cache judge outputs; smaller judge model with a fixed seed |
| Scope creep — this is a large system for one semester | Phase gates; phases 0–5 + 8 constitute a defensible project on their own; 9 and 11 are polish |
| Fabricating institutional facts (fees, placement figures) that look real | Anything not verifiable from a public source is authored as demo with an obviously-synthetic identifier |

---

## 9. Decisions

### 9.1 Settled (confirmed 28 Aug 2026)

| # | Decision | Outcome |
|---|---|---|
| 1 | **UI deviation (§0.3 A)** | ✅ **Approved.** Next.js + FastAPI portal; RAG core unchanged (LangChain/LangGraph/Ollama/Chroma); Streamlit retained for the RAGAS evaluation console. Report §3.2 gains one sentence explaining the interface upgrade. |
| 2 | **Hardware** | ✅ **16 GB+ available.** Generator: `qwen2.5:7b-instruct-q4_K_M`. Judge: `llama3.1:8b-instruct-q4_K_M` (different family, so no self-judging). Reranker stays resident. Report Table 3.1 should be updated from 8 GB to the actual demo machine's spec. |
| 3 | **Vector store** | ✅ **ChromaDB**, persisted to `./data/chroma` — matches Report Table 3.2 and supports the metadata filtering hybrid retrieval needs. FAISS kept behind the same interface if a speed comparison is wanted for the report. |
| 4 | **Auth scope** | ⚙️ **No preference given → proceeding with public portal + admin-only.** Public browsing and Ask PCE for everyone; a single `admin` role gates ingestion, corpus management and the evaluation centre. The `users.role` enum still carries `student`/`faculty`, so full RBAC can be switched on later without a migration. Say the word if you'd rather have the four-role version. |

| 5 | **Repo hygiene** | ✅ **Approved.** `.gitignore` added; `.gitattributes` tracks `*.docx`, `*.pdf`, `*.pptx` and other large binaries via **Git LFS**. The repo has zero commits, so LFS applies cleanly from the first commit — no history rewrite needed. |
| 6 | **Supervisor sign-off** | ✅ **Non-blocking.** Verbal approval for the Streamlit→Next.js UI change and the reduced auth scope (public + admin-only, student/faculty roles deferred) is being obtained separately by the team. Development proceeds as planned; if either decision is reversed, the team will say so explicitly. |

### 9.2 Reversal notes

Both deferred decisions were designed to be cheap to reverse, and it is worth recording why:

- **Auth scope** — `users.role` is declared as a four-value enum (`guest`, `student`, `faculty`, `admin`) from the first migration. Turning on student/faculty roles later is route guards and seed data, not a schema migration.
- **UI** — the RAG core is a Python package with no knowledge of the transport layer. If the primary UI had to revert to Streamlit, the knowledge service, retrieval engine, agentic layer and evaluation harness are all unaffected; only `frontend/` and the thin FastAPI route layer would be discarded.

### 9.3 Still open

Nothing. Phase 0 is cleared to proceed.

---

---

## 10. Phase 0 completion record (28 Aug 2026)

### 10.1 What was built

45 files. `backend/` (FastAPI app, settings, structured logging with per-request
trace IDs, DB session layer, liveness + readiness endpoints, tests),
`backend/alembic/` (env wired to app settings, baseline revision),
`docker-compose.yml` (postgres 16, redis 7, chroma 0.6.3, ollama, ollama-init
model puller, api — health checks on all five long-running services),
`.env.example` (61 keys), `.gitignore`, `.gitattributes` (Git LFS),
`Makefile`, `README.md`, `.github/workflows/ci.yml`, `scripts/bootstrap.sh`,
`scripts/verify-stack.sh`, and placeholder READMEs for `rag/`, `eval/`,
`frontend/`, `corpus/demo/`.

### 10.2 What was verified, and what could not be

**No Docker daemon was available in either environment used to build this** —
neither the cloud workspace nor the sandboxed VM that reaches the repo folder
has one, and both have PyPI blocked. So `docker compose up` was *not* executed,
and the runtime health checks are *not* confirmed. That confirmation is the
team's to produce, with one command, on the 16 GB Mac.

| Check | Result |
|---|---|
| `ruff check` (E, F, W, I, N, UP, B, C4, SIM, ARG, PTH) | clean — 2 real defects found and fixed |
| `ruff format --check` | clean across 16 files |
| Python 3.11 compilation, all modules | clean |
| `Settings` behaviour executed for real (URL composition, CORS parsing, caching, ablation flags) | 7/7 assertions pass |
| Every `Settings` field documented in `.env.example` | 48/48 |
| `docker-compose.yml` parses; `depends_on` targets exist; every `service_healthy` target has a health check; every named volume declared; `$$` escaping correct | clean |
| CI workflow YAML parses; 3 jobs resolve | clean |
| `bash -n` on both shell scripts | clean |
| `.gitignore` correctness against the real repo | 45 files untracked, 0 `__pycache__` leaks; one real bug found and fixed (`data/` → `data/*`, since git will not descend into an excluded directory to honour a negation) |
| `pytest` | **not run** — FastAPI could not be installed (PyPI blocked). Runs in CI and on the team's machine. |
| `mypy` | **not run** — its pydantic plugin needs pydantic installed. Runs in CI. |
| `docker compose up`, health checks, model pulls | **not run** — no Docker daemon. Run `./scripts/verify-stack.sh`. |

### 10.3 Before the first commit

`git-lfs` is **not** installed on the machine that built this, and the repo
still has zero commits. Install it and initialise it *before* the first commit,
or the 11 MB `.docx` goes into git history as an ordinary blob and removing it
later means rewriting history:

```bash
brew install git-lfs
cd majorproject2026 && git lfs install
git add -A && git commit -m "Phase 0: foundations"
git lfs ls-files        # must list the .docx and .pdf
```

### 10.4 Gate

Phase 1 (corpus acquisition) does not begin until the team has run
`./scripts/verify-stack.sh` and given explicit go-ahead.

**Sources consulted:** [PCE homepage](https://www.pce.ac.in/) · [The Institute](https://www.pce.ac.in/about/the-institute/) · [B.Tech programmes](https://www.pce.ac.in/academics/bachelors/) · [NAAC](https://www.pce.ac.in/accreditation/naac/) · [NBA](https://www.pce.ac.in/accreditation/nba/) · [NIRF](https://www.pce.ac.in/accreditation/nirf/) · [Admissions FAQ](https://admissions.pce.ac.in/faq) · [PCE Annual Report AY 2023-24](https://www.pce.ac.in/wp-content/uploads/2025/02/Final-PCE-Annual-Report-for-A.Y-2023-24.pdf) · `Docs/Report final (1).docx` · `Docs/survey paper (1).pdf`

---

## 11. Phase 1 record (28 Aug 2026)

### 11.1 What was built

`rag/ingestion/` — 15 modules, 6 test modules, **113 tests passing**.

| Module | Responsibility |
|---|---|
| `models.py` | `ParsedDocument`, `Section`, `DocumentCategory`, `SourceType`; `validate()` enforces the corpus invariants |
| `categorise.py` | URL → category and department rules; skip patterns |
| `robots.py` | `robots.txt` compliance and `Crawl-delay`, via the standard library |
| `crawler.py` | Sequential, cached, sitemap-seeded crawler |
| `parsers/sections.py` | Markdown → heading tree (the structure-aware foundation) |
| `parsers/html.py` | Boilerplate-stripped extraction, trafilatura with a BeautifulSoup fallback |
| `parsers/pdf.py` | Page-accurate extraction; TOC → font-size → per-page strategies |
| `parsers/markdown.py` | Demo loader; front matter mandatory, non-compliant files rejected |
| `normalise.py` | Validated write of `.md` + `.json` per document |
| `manifest.py` | Provenance record and real/demo accounting |
| `cli.py` | `crawl` / `parse` / `manifest` / `stats` / `all`, plus a dependency preflight |

Demo corpus: **19 documents, 149 sections, ~8,200 words** — 4 SOPs, 4 circulars,
4 internal wiki pages, 3 lab manuals, 3 helpdesk articles, 1 timetable. Every
one carries mandatory front matter with a stated `demo_reason`, and all figures
in them are illustrative rather than plausible institutional fact.

### 11.2 Three invariants that are enforced rather than documented

1. A document in an internal-only category (`sop`, `circular`, `internal_wiki`,
   `lab_manual`, `helpdesk`, `timetable`) **cannot** be marked real. This
   material does not exist publicly, so a real-labelled instance is a bug and
   `validate()` says so.
2. A demo document **must** carry a `demo_reason` of at least a sentence. A
   file under `corpus/demo/` without compliant front matter is rejected, not
   defaulted.
3. A PDF-sourced document **must** carry page numbers on its sections, because
   page-level provenance is a project requirement rather than a nicety.

There is no `--ignore-robots`. The flag exists only to be refused with an
explanation.

### 11.3 What was verified

| Check | Result |
|---|---|
| `pytest rag/tests` | **113 passed** |
| `ruff check` + `ruff format --check` on `rag/` | clean (17 findings fixed) |
| Ingestion run end to end on the demo corpus | 19 parsed → 19 normalised → manifest written → statistics printed |
| Content-hash skip logic | second run reported "unchanged 19" — no needless rewrites |
| BeautifulSoup fallback path | exercised for real, with trafilatura absent |
| Dependency preflight | warns correctly with trafilatura and PyMuPDF absent |
| **The crawl** | **not run** — no network egress to pce.ac.in from either build environment |

Three real defects were found by running the code rather than reading it:

- **Department inference never matched document text.** The rules are written
  URL-style (`computer-engineering`) but were also applied to prose, where the
  name appears as "Computer Engineering". Fixed by folding whitespace to
  hyphens in one place so a single ruleset serves both.
- **`doc_id`s containing slashes became directory paths.** `DEMO/EXAM/2026/03`
  is what a circular number actually looks like, and flattening it would make
  the corpus less faithful — so the identifier is kept and a separate
  `file_stem` property derives the filename. Caught only by the end-to-end run.
- **A missing HTML extractor would have dropped every page silently**, ending
  the run with "0 real documents" and no explanation. Now a preflight check.

### 11.4 What the team must run

```bash
docker compose up -d --build          # rebuild: requirements.txt gained Phase 1 deps
docker compose exec api python -m rag.ingestion all
```

The crawl is polite by construction — sequential, ≥1s between requests,
robots-compliant — so expect roughly **15–25 minutes** for a few hundred pages.
Every response is cached under `corpus/raw/`, so `parse` and `manifest` can be
re-run freely afterwards without touching the site again.

### 11.5 The ratio, resolved

The crawl returned **600 real documents**, putting the demo share at 3.1% — and
the tool flagged that as off-target. Investigating the flag rather than obeying
it turned up two things.

**The check itself was wrong.** `meets_target` was implemented as a two-sided
band, `abs(demo_share - 0.20) <= 0.07`, so a corpus that is 96.9% real was
reported as a failure. The brief asks for "~80% real, ~20% clearly labelled
demo", and the guarantee that matters there is a **floor on real data**. Being
more real than the target is not a defect. The check is now one-sided:

```python
MIN_REAL_SHARE = 0.80
meets_target = real_share_by_document >= MIN_REAL_SHARE
```

Demo share is still reported — by document count and by word count — because it
answers a different question: is there enough internal-document coverage to
evaluate that path? That is settled by counting golden-set questions, not by a
percentage.

**Obeying the flag would have cost 96–173 fabricated documents**, and the
number grows with the corpus:

| Real documents | Demo docs for the old 13% floor | for 20% exactly |
|---|---|---|
| 600 | 90 | 150 |
| 770 (after the PDF fix) | 115 | 192 |
| 800 | 120 | 200 |

At 20% of 770 real documents, roughly one in five things the system "knows"
would be invented. That is a worse project than one that is 95% real, whatever
the brief's arithmetic says.

**What was done instead:** 20 further demo documents, sized by what Chapter 4
needs — enough coverage across all six internal-only categories to support
20–25 golden-set questions. The demo corpus is now **39 documents, 313
sections, 16,579 words**, up from 19 / 149 / 8,165.

| Category | Documents |
|---|---|
| SOP | 8 |
| Circular | 8 |
| Internal wiki | 8 |
| Lab manual | 6 |
| Helpdesk | 6 |
| Timetable | 3 |

Projected combined corpus after the PDF fix: **~809 documents, ~707,000 words,
95.2% real** — comfortably above the floor.

Two of the new documents deliberately contain **no contact numbers at all**
(the medical emergency SOP and the anti-ragging circular). A fabricated
emergency or reporting number that a user mistook for genuine could cause real
harm, so those documents name the office to ask instead. Where monetary or
quota figures were unavoidable — procurement bands, print quotas, late fees —
they carry an explicit "illustrative placeholder" banner.

`python -m rag.ingestion manifest --strict` exits non-zero when the real share
falls below the floor, so this can gate CI.

### 11.6 The PDF defect

The first crawl fetched **170 PDFs** and parsed none of them, silently. The
crawler writes a PDF as `<slug>.pdf.pdf` — the URL slug already ends in `.pdf`
and the writer appends the suffix — while the parser reconstructed the name
with `Path.with_suffix(".pdf")`, which *replaces* the final suffix rather than
appending. It looked for `<slug>.pdf`, found nothing, and fell through to a
`continue`.

Those PDFs are the annual reports, NAAC and NIRF submissions, term calendars
and brochures: the only documents in the corpus that can carry **page-level
provenance**, which is a stated project requirement. The corpus was missing its
most valuable material and said nothing about it.

Fixed by deriving the body filename from the sidecar's stem by concatenation,
never by `with_suffix`. New crawls also record `local_path` in the sidecar, so
the writer and reader can no longer disagree. Four regression tests pin the
round trip in both directions, and a PDF whose body file is missing is now
reported as a corpus gap rather than skipped. **No re-crawl is needed** — the
PDFs were cached correctly all along.

### 11.7 Gate

Phase 2 (data layer) does not begin until the team has re-run `parse` and
`manifest` with the PDF fix and shared the resulting statistics.

---

## 12. Phase 1.1 — corpus quality (28 Aug 2026)

The Phase 1 gate passed on the second run: **823 documents, 784 real, 95.3%
real, `meets_target` True**, with 145 PDFs now parsed and carrying page-level
provenance. Inspecting the manifest rather than accepting the summary turned up
four defects, one of them material to the evaluation.

### 12.1 Duplicate content — 11.8% of the corpus

**97 of 823 documents had byte-identical extracted text**, in 19 groups. The
largest was **68 documents**: `/accreditation/`, `/accreditation/nba/`,
`/iqac/` and 65 other hub pages whose only substantive block was the same
shared "Departments" table. About 42,600 redundant words.

This is not a tidiness problem. Retrieval would have returned the same table
five times for a single question, filling the entire context budget with one
block. **Context Precision** — one of the three RAGAS metrics Chapter 4 must
report — measures precisely that, so the duplicates would have depressed a
headline result for a reason having nothing to do with the retrieval strategy
under evaluation. The ablation between C0 and C5 would have been measuring
corpus hygiene.

`rag/ingestion/dedupe.py` now groups by `content_hash` and keeps one document
per group: real over demo, then shallowest URL path, then shortest URL and
doc_id — the last two arbitrary but deterministic, so repeated parses do not
churn the manifest.

Suppression is recorded, never silent. Every dropped document keeps its URL in
`corpus/suppressed.json` and in the manifest's `suppressed_duplicates`,
alongside the document carrying its content.

### 12.2 Three smaller defects

**HTML entities were never decoded in titles.** Every title read
"Accreditation &#8211; PCE". Worse, because the entity was not decoded, the
WordPress suffix stripper — which looks for a real en dash — never fired, so
every title also kept the site name. One missing `html.unescape()` produced two
visible defects in every citation the user would ever see.

**The frontier carried un-normalised URLs.** `_enqueue` normalised only for its
dedup set and returned a bool, so the caller queued the raw string. Four URLs
kept their `#fragment` into the fetch and into the recorded provenance. It now
returns the normalised URL, or None.

**Cache filenames were non-deterministic.** `_paths_for` derived the filename
for a query-string URL with Python's `hash()`, which is randomised per process.
The same URL therefore got a different filename on every run: the cache never
hit and pce.ac.in was re-fetched in full each time. For a crawler pointed at
someone else's live server that is a politeness defect, not a performance one.
Now a stable SHA-1 digest. Static assets carrying cache-busting query strings
(`style.css?ver=6.9.7`) are also skipped now — the extension is matched against
the path rather than the whole URL.

### 12.3 Verification

| Check | Result |
|---|---|
| `pytest rag/tests` | **145 passed** (up from 119) |
| `ruff check` + `ruff format --check` | clean |
| Deduplication end to end | 7 hub pages sharing one body → 1 kept, 6 suppressed and recorded |
| Title decoding | `Accreditation &#8211; PCE` → `Accreditation` |
| Cache determinism | same filename across three separate processes |
| Frontier normalisation | `x.pdf#new_tab` → `x.pdf`; second spelling refused |
| Suppression count in manifest statistics | recorded (was silently zero on the first attempt) |

### 12.4 What the team must run

```bash
docker compose exec api python -m rag.ingestion parse
docker compose exec api python -m rag.ingestion manifest
```

Re-parse only — **no re-crawl**. Expected: roughly 726 documents kept, ~97
suppressed and listed in `corpus/suppressed.json`, real share still comfortably
above the 80% floor, and titles that read properly in citations.

The crawler fixes apply to the next crawl. Note that the cache-filename change
means query-string URLs (`?p=2075` and similar, mostly WordPress permalink
redirects) will be re-fetched once on the next crawl; the 784 real documents
already on disk are unaffected.

### 12.5 Gate

Phase 2 begins once the team has re-parsed and confirmed the deduplicated
figures.

---

## 13. Phase 1.2 — the deduplication that wasn't (28 Aug 2026)

The Phase 1.1 re-parse reported **823 documents kept and 214 duplicates
dropped**. Those two numbers cannot both come from one parse: if 214 were
dropped from a set that parsed to 823, the kept set is 609.

Checking the disk rather than the summary:

```
normalised .json on disk        823
suppressed.json entries         214
files written in the last parse   3
suppressed docs still on disk   200 of 214
duplicate content still present  97 redundant, 19 groups
```

**`normalise()` only ever added files.** It had no concept of removing a
document that should no longer be in the corpus, so every suppressed duplicate
kept its `.json` and `.md`, `load_documents()` read them straight back off
disk, and the manifest described a corpus that still contained everything it
claimed to have dropped. The deduplication computed correctly and then had no
effect. My bug, introduced in Phase 1.1.

It also explains the 214-versus-97 discrepancy. 214 is the honest redundancy in
a clean parse; the 97 measured earlier was itself taken from a directory
already polluted by leftovers from previous runs. Every count in this corpus
had been quietly drifting for three runs.

### 13.1 The fix

`normalise()` now prunes: after it returns, `corpus/normalised/` contains
exactly the documents passed in and nothing else. The directory is a generated,
gitignored artefact, so treating it as derived state is safe. Two guards:

- An **empty document list does not prune**. A parse that failed outright must
  not delete a good corpus on the strength of having produced nothing.
- Only `.json` and `.md` are considered. Anything else in the directory is left
  alone.

`parse` now also reconciles and prints:

```
reconciled: parsed 45, suppressed 4, kept 41, on disk 41
```

and warns loudly when those disagree. A silent drift between what a run decided
and what is on disk is exactly how this defect hid for three runs, so the tool
now states the relationship every time rather than leaving it to be inferred
from a manifest later.

### 13.2 Verification

| Check | Result |
|---|---|
| `pytest rag/tests` | **150 passed** (up from 145) |
| `ruff check` + `ruff format --check` | clean |
| Pollution reproduced then cleaned | 45 files with dedup off → parse → 8 pruned → 41 on disk, matching kept exactly |
| Redundant documents remaining after a real parse | **0** |
| Manifest self-consistency | `len(documents) == distinct content_hash` → True |
| Empty parse against a populated corpus | pruned nothing, corpus intact |

### 13.3 What the team must run

```bash
docker compose exec api python -m rag.ingestion parse --force
docker compose exec api python -m rag.ingestion manifest
```

`--force` matters this once. The content-hash skip means unchanged documents
are not rewritten, and the corpus on disk is three runs of drift deep; a forced
pass rewrites everything from the current parsers and prunes the rest.

Expect roughly **609 documents kept, 214 suppressed**, zero redundant content,
and a `reconciled:` line where kept and on-disk agree.

### 13.4 Gate

Phase 2 schema and migrations do not depend on corpus contents and can be built
in parallel. The **seed step** does, so it is run only after the reconciled
figures come back.

---

## 14. Phase 2 — data layer (28 Aug 2026)

### 14.1 What was built

**27 tables** across three domain modules, matching §4.

| Module | Tables |
|---|---|
| `app/models/institutional.py` | departments, programs, courses, faculty, announcements, events, facilities, placements, accreditations, contacts |
| `app/models/knowledge.py` | documents, document_sections, chunks, suppressed_documents |
| `app/models/interaction.py` | users, chat_sessions, chat_messages, message_citations, retrieval_logs, verification_results, feedback, eval_datasets, eval_questions, eval_runs, eval_results, ingestion_jobs, audit_logs |

Plus `app/models/enums.py` (14 native PostgreSQL enum types), `app/models/mixins.py`
(the UUID primary key and the `is_demo` column, declared once so no table can
omit either), and `app/seed/` (reference data, corpus loader, admin account).

### 14.2 Design decisions worth recording

**UUID primary keys, not sequences.** Chunk identifiers are mirrored into
Chroma as external keys. A UUID can be minted before the row exists and
survives a dump-and-reload; a sequence does not.

**`is_demo` denormalised onto chunks and citations.** It is set once at
ingestion and copied forward. Retrieval never joins back to the document to
learn whether it is about to cite synthetic data, so the DEMO badge cannot be
lost by a query that forgot a join. A test asserts the column exists and is
non-nullable on all twelve tables that can carry institutional fact.

**Provenance enforced by a constraint.** `ck_documents_has_provenance` requires
`source_url` or `local_path`. A document traceable to nowhere cannot be
inserted, rather than merely being discouraged.

**`retrieval_logs` stores every stage.** Rewritten queries, dense and sparse
candidates, the fused ranking, the reranked ranking, per-stage latency. Every
ablation number in Chapter 4 becomes a query against this table instead of a
re-run of both configurations under conditions one hopes matched.

**Four user roles from the first migration** even though the approved scope
uses one. Enabling student and faculty later is route guards and seed data
rather than an enum migration on a populated table.

**Enum types created in their own revision.** Several enums are shared between
tables (`run_status` by `eval_runs` and `ingestion_jobs`); if SQLAlchemy owned
their creation it would emit CREATE TYPE once per table and fail on the second.
Every Enum sets `create_type=False` and revision `0002_enum_types` is the one
place they are created and dropped.

### 14.3 An honest limitation, and the guard for it

**SQLAlchemy could not be installed in either build environment** (PyPI is
blocked), so the models were never imported, no metadata was ever built, and
the table DDL was never executed. Everything here is syntax-checked, linted
and cross-checked, but not *run*.

Writing 27 tables of migration DDL by hand under that constraint would be
reckless, so the table migration is **generated on the team's machine** by
Alembic autogenerate — which derives it from the models themselves and cannot
mistranscribe them — and `tests/test_schema.py` is the guard:

| Test | What it catches |
|---|---|
| `test_migrations_leave_no_drift_against_the_models` | Applies every migration to an empty database, then diffs the result against `Base.metadata` with `compare_metadata`. Any missing column, wrong type or absent index fails the build. |
| `test_declared_enum_members_match_the_python_enums` | Migration `0002` and `app/models/enums.py` disagreeing |
| `test_the_migration_declares_every_enum_the_models_use` | A model gaining an enum whose type was never created |
| `test_document_categories_are_a_superset_of_the_pipeline_s` | The API enums drifting from the pipeline's, which are deliberately duplicated rather than imported |
| `test_every_table_has_a_primary_key` / `has_timestamps` | Structural omissions |
| `TestDemoFlagPropagation` (24 cases) | Any of the twelve fact-carrying tables losing `is_demo`, or it becoming nullable |

The drift check runs in CI against a PostgreSQL service container, so a model
change merged without its migration fails the build rather than surfacing as a
missing column at runtime.

Verified without a database: 14 enum types cross-checked value-by-value between
`enums.py` and migration `0002` (no mismatches); the pipeline's document
categories and source types confirmed to be subsets of the API's; ruff lint and
format clean across all new modules; every module compiles under Python 3.11.

### 14.4 What the team must run

```bash
# 1. Re-parse with the Phase 1.2 pruning fix
docker compose exec api python -m rag.ingestion parse --force
docker compose exec api python -m rag.ingestion manifest

# 2. Rebuild the image — requirements are unchanged, but the code is not
docker compose up -d --build

# 3. Create the enum types
docker compose exec api alembic upgrade head

# 4. Generate the table migration FROM the models
docker compose exec api alembic revision --autogenerate \
    -m "institutional, knowledge and interaction schema"

# 5. Apply it, then prove it matches the models
docker compose exec api alembic upgrade head
docker compose exec api pytest tests/test_schema.py -v

# 6. Seed
docker compose exec api python -m app.seed
```

Step 5 is the one that matters. If `test_migrations_leave_no_drift_against_the_models`
passes, the schema on disk and the models agree, and the generated migration
can be committed with confidence. If it fails, it names exactly what differs.

The seed prints a contents summary. Expect 6 departments, 6 B.Tech programmes
totalling an intake of 630, 4 accreditation records, and documents matching the
reconciled corpus count with roughly 95% real and 145 carrying page numbers.

`app/seed/reference.py` holds only facts confirmed from a public page, each
with its source URL, and the seed asserts the six intakes sum to the 630 the
bachelors page states — so a typo fails loudly rather than surfacing when
someone asks the assistant for the total.

### 14.5 Gate

Phase 3 (baseline RAG, configuration C0) begins once the schema test passes and
the seed reports its counts.

---

## 15. Phase 2.1 — the duplicate enum type (28 Aug 2026)

`alembic upgrade head` failed on a genuinely empty database:

```
psycopg.errors.DuplicateObject: type "accreditation_body" already exists
[SQL: CREATE TYPE accreditation_body AS ENUM ('naac', 'nba', ...)]
```

### 15.1 Cause

The autogenerated table migration rendered every enum column as
`sa.Enum('naac', ..., name='accreditation_body')` — **without**
`create_type=False`. On PostgreSQL that form creates the type as part of
`CREATE TABLE`, and revision `0002_enum_types` had already created it.

The models do set `create_type=False`, but that never reaches the generated
file: **autogenerate re-renders a type from its name and values alone** and
does not carry construction arguments across. So the setting that makes the
design work was silently dropped at exactly the point it mattered.

The failure was worse than a collision with `0002`. Six of the fourteen types
are used by more than one table:

| Type | Tables |
|---|---|
| `run_status` | eval_runs, ingestion_jobs |
| `source_type` | documents, (chunk metadata) |
| `ingest_status`, `question_type`, `verification_status`, `entailment_label` | two tables each |

So the generated migration would have failed on the **second** table using a
shared type even with `0002` deleted entirely. Removing `0002` was not an
available fix; `create_type=False` was required either way.

### 15.2 Fix

**Root cause — `alembic/env.py` gains a `render_item` hook.** Autogenerate now
emits `postgresql.ENUM(..., create_type=False)` for every enum column, so
regenerating the schema can no longer reintroduce the fault.

**The existing file — rewritten in place.** All 15 enum column definitions
converted, with the `postgresql` dialect import added. The rewrite scanned for
the balanced closing parenthesis rather than pattern-matching, so a value
containing a bracket could not truncate a call, and the result was re-parsed as
Python before being written.

Downgrade is correct as generated: with `create_type=False` the table drops no
longer attempt `DROP TYPE`, leaving `0002` to own that, in the right order.

### 15.3 The guard

Three new tests in `tests/test_schema.py`, none of which need a database:

| Test | Catches |
|---|---|
| `test_no_migration_uses_bare_sa_enum` | Any migration creating a type during CREATE TABLE |
| `test_every_enum_column_disables_type_creation` | A `postgresql.ENUM` missing `create_type=False` |
| `test_the_env_hook_that_keeps_this_true_is_present` | `render_item` being lost from `env.py`, which would make the next autogenerate silently undo the fix |

Verified by running the same checks against both the fixed files and the backup
of the broken one: clean on the former, and the broken file is correctly
identified on the latter. The check takes seconds and needs no container, so
this class of defect now fails before a build rather than after one.

### 15.4 Verified, and not

| Check | Result |
|---|---|
| 15 enum columns rewritten, 0 bare `sa.Enum` remaining | pass |
| All 15 carry `create_type=False` | pass |
| 14 enum type names in the table migration match `0002` exactly, values included | pass |
| Migration file re-parses as valid Python | pass |
| `env.py` compiles and references `render_item` in both configure paths | pass |
| Downgrade attempts no `DROP TYPE` | pass |
| **`alembic upgrade head` actually run** | **not possible here** — no PostgreSQL and no SQLAlchemy in either build environment |

### 15.5 What the team must run

```bash
docker compose down -v && docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api pytest tests/test_schema.py -v
docker compose exec api python -m app.seed
```

No regeneration needed — the existing migration is fixed in place. If the
schema is ever regenerated, `render_item` now makes the output correct by
default.

---

## 16. Phase 2.2 — 27 documents that never reached the database (28 Aug 2026)

The seed reported **582 documents**. The manifest holds **609**. Both numbers
were reported as a success.

```
manifest documents            609
normalised .json on disk      609
loaded into the database      582     <- 27 documents missing
docs the seed could not find   27
docs actually missing           0     <- every file was on disk all along
```

### 16.1 Cause

`ParsedDocument.file_stem` slugifies `doc_id` and **truncates at 80
characters**. Twenty-seven doc_ids are longer than that — up to 86 — so their
files were written under the truncated name.

`app/seed/corpus.py` did not use `file_stem`. It **reimplemented** the
derivation:

```python
stem = re.sub(r"[^a-z0-9]+", "-", doc_id.replace("/", "-").lower()).strip("-")
```

…and omitted the truncation. For a long id it therefore looked for an 86-
character filename that has never existed, found nothing, and skipped the
document.

This is the same class of defect as the crawler's `.pdf.pdf` failure in Phase
1: **one transformation, implemented twice, drifted apart.** Both times the
writer was right, the reader was wrong, and the loss was silent.

### 16.2 Fix

**`file_stem` is now carried in the manifest.** The pipeline writes it; the
seed reads it. Nothing downstream re-derives a lossy transformation.

**The fallback calls the pipeline's own `slugify`** rather than reimplementing
it, for manifests written before the field existed — which is why the 27
documents are recoverable without regenerating anything.

**Collisions are now refused, not absorbed.** Truncation means two long ids
sharing an 80-character prefix map to one filename, and the second would
overwrite the first — the manifest listing both while only one existed.
`normalise()` detects this before writing anything and `parse` aborts with a
non-zero exit and the offending pair named. There are no collisions in the
current corpus; the guard is there because there is no reason there could not
be.

**The seed reconciles and refuses to call a partial load a success:**

```
reconciled: manifest 609, loaded 609, skipped 0
```

A shortfall now raises. A corpus quietly missing 27 documents is a retrieval
system that quietly cannot answer questions about them, and reporting that as
success is worse than failing.

### 16.3 Verification

| Check | Result |
|---|---|
| `pytest rag/tests` | **158 passed** (up from 150) |
| All 609 manifest documents resolvable with the fix | pass (0 unresolvable) |
| Long doc_id truncates to exactly 80 chars, and the file written matches | pass |
| Naive re-derivation demonstrably finds nothing | pass — pins the exact defect |
| Shared `slugify` reproduces `file_stem` for pathological ids | pass |
| Two ids sharing an 80-char prefix detected as a collision | pass |
| Nothing written when a collision exists | pass |
| ruff lint and format | clean |

### 16.4 What the team must run

```bash
docker compose exec api python -m rag.ingestion manifest   # adds file_stem
docker compose exec api python -m app.seed corpus
```

Expect `reconciled: manifest 609, loaded 609, skipped 0` and 609 documents in
the database — 570 real, 39 demo, about 93.6% real.

### 16.5 Why this gates Phase 3

Phase 3 builds the C0 baseline index from the documents in the database. That
index, and the numbers measured against it, become the reference point every
later configuration is compared to in Chapter 4. Building it over a corpus
missing 27 documents means rebuilding it — and worse, means the C0 figures
would not be comparable to C1-C5 measured later over the full corpus.

One minute of re-seeding now avoids invalidating the baseline.
