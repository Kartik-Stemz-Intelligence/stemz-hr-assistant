# Stemz HR Assistant — Phase 1

Grounded RAG chatbot for HR policy Q&A. **Phase 1 scope**: single document
(attendance policy), Django backend, clean Tailwind chat UI, in-memory
retrieval, streaming responses, refusal below confidence threshold — no
hallucination, no vector DB.

## What Phase 1 proves

1. The bot answers policy questions **only** from the ingested document, with
   a `Source:` citation on every answer.
2. When a question is out of scope (or the top-retrieval score falls below
   `SIM_THRESHOLD`), the bot returns a **verbatim refusal message** without
   ever calling the LLM.
3. The RAG loop — ingest → retrieve → guardrail → generate — is modular and
   swappable for later phases (multi-doc, pgvector, personalisation, Keka
   integration).

## Quick start

```bash
# 1. Create a virtualenv (Python 3.11+ recommended)
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell / cmd
# source .venv/bin/activate  # macOS / Linux

# 2. Install dependencies (first install may take a few minutes — torch is large)
pip install -r requirements.txt

# 3. Set up environment
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux
# then edit .env and set your ANTHROPIC_API_KEY

# 4. Run Django migrations
python manage.py migrate

# 5. Ingest the attendance policy (downloads the embedding model on first run)
python manage.py ingest_docs

# 6. Run the dev server
python manage.py runserver
```

Open **http://localhost:8000/** and start chatting.

## Try these questions

**Grounded (should answer with a `Source:` citation):**

- How many late arrivals are allowed per month?
- How many WFH days can I take per month?
- What is the notice period for a WFH request?
- Can I raise an OD request for a past date?
- What happens if I miss a swipe?

**Out of scope (should return the refusal message):**

- What is the maternity leave policy?
- How much salary will I get this month?
- What stock should I invest in?

## Run the eval baseline

```bash
pytest
```

This runs the attendance-policy Q&A baseline (7 grounded + 4 refusal cases).
Every future change (chunk size, embeddings, threshold, model swap) must keep
these tests green.

## Project structure

```
hr-assistant/
├── manage.py
├── requirements.txt
├── pytest.ini
├── .env.example
├── config/
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   └── dev.py              # Local development
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── knowledge/              # Document ingestion pipeline
│   │   ├── services/
│   │   │   ├── parser.py       # Markdown + frontmatter → chunks
│   │   │   ├── embedder.py     # bge-small-en-v1.5 wrapper (swappable)
│   │   │   └── ingest.py       # Orchestrator
│   │   └── management/commands/ingest_docs.py
│   ├── rag/                    # RAG loop — independent of UI
│   │   ├── services/
│   │   │   ├── retrieve.py     # Cosine similarity top-k
│   │   │   ├── guardrail.py    # Threshold refusal (no LLM call)
│   │   │   └── generate.py     # Grounded prompt → Claude streaming
│   │   └── prompts/grounding.py
│   └── chatbot/                # UI + endpoints
│       ├── models.py           # Conversation, Message (audit log)
│       ├── views.py            # SSE streaming endpoint
│       ├── urls.py
│       └── templates/chatbot/
│           ├── base.html
│           └── chat.html
├── knowledge/
│   └── attendance-policy.md    # Source document
├── data/                       # Generated at ingest time
│   ├── chunks.json
│   └── embeddings.npy
└── tests/
    ├── conftest.py             # Auto-ingest fixture
    └── test_eval_baseline.py   # Regression eval bank
```

## Config (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Model for generation |
| `SIM_THRESHOLD` | `0.35` | Below this top score → refuse without LLM call |
| `TOP_K` | `4` | Number of chunks retrieved per query |
| `DJANGO_SECRET_KEY` | *(dev fallback)* | Django secret |
| `DJANGO_DEBUG` | `True` | Debug mode |

## How the RAG loop works (a quick tour)

1. **Ingest** (`manage.py ingest_docs`)
   - Reads `knowledge/attendance-policy.md`
   - Parses YAML frontmatter (document, version, effective_date)
   - Splits body by `##` headings into semantic chunks
   - Embeds each chunk with `BAAI/bge-small-en-v1.5` (local, free)
   - Saves `data/chunks.json` + `data/embeddings.npy`

2. **Retrieve** (`apps/rag/services/retrieve.py`)
   - Embeds the user query with the same model
   - Computes cosine similarity against all chunk embeddings
   - Returns top-K chunks with scores

3. **Guardrail** (`apps/rag/services/guardrail.py`)
   - If `top_score < SIM_THRESHOLD`, returns the refusal message immediately
   - **No LLM call is made** — this is the primary anti-hallucination lever

4. **Generate** (`apps/rag/services/generate.py`)
   - Formats retrieved chunks as numbered `<context>` excerpts
   - Sends grounding system prompt + user query to Claude
   - Streams tokens back to the UI via Server-Sent Events

5. **Log** (`apps/chatbot/models.py`)
   - Every Q&A is logged with the retrieved chunk titles and top score
   - Feeds later phases (analytics, KB-gap detection, eval bank growth)

## What Phase 1 intentionally excludes

- Multiple documents (Phase 2)
- Real vector store — Chroma/pgvector (Phase 2)
- Candidate-uploaded personal docs / offer letter (Phase 3)
- Personalised salary explainer (Phase 3)
- Full lifecycle memory / stage awareness (Phase 4)
- Keka read-only integration (Phase 5)
- Voice input, HR admin panel, analytics dashboard (Phase 6)
