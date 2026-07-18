# Enterprise AI Knowledge & Engineering Assistant

Upload internal engineering documents (manuals, specs, test reports,
requirements) and ask questions over them in plain English, with every
answer traceable back to the exact file and page it came from. Also
generates executive summaries and pulls out requirements / action items
automatically.

This is not "ChatGPT with a PDF" -- it's an engineered platform: modular
code, JWT auth, structured logging, config management, automated tests,
Docker, and a documented REST API.

## Architecture

```
                          Client
                            |
                       FastAPI app (app/main.py)
                            |
        +-------------------+--------------------+
        |                   |                    |
   Auth Router          Upload Router        Chat / Search Router
   (JWT login)        (ingest documents)     (ask questions)
        |                   |                    |
        |                   v                    v
        |            Document Service  <--  RAG Pipeline
        |            (loader/chunker/           |
        |             embeddings)               v
        |                   |             FAISS Vector Store
        |                   +--------------------+
        v
   User Store (JSON)
```

Data flow for a question:

```
question --> embed --> FAISS similarity search --> top-k chunks
         --> LLM (or extractive fallback) --> answer + [file, page] sources
```

## Folder structure

```
enterprise-ai-platform/
├── app/
│   ├── main.py              # FastAPI app, router wiring, request logging
│   ├── core/                # config, logging, JWT/password helpers
│   ├── auth/                # register/login/logout, JWT dependency
│   ├── models/               # User store, DocumentMeta
│   ├── rag/                  # loader, chunker, embeddings, FAISS store, pipeline
│   ├── services/             # document_service, analysis_service (summary/requirements)
│   ├── api/                   # HTTP routers: upload, chat, search, documents, health
│   └── tests/                 # pytest suite (18 tests)
├── data/                       # uploads, vector store, users.json, logs (gitignored)
├── docker/, Dockerfile, docker-compose.yml
├── scripts/smoke_test.py       # end-to-end smoke test against a live server
├── requirements.txt
└── .env.example
```

## Features

- **Auth**: register / login / logout, JWT bearer tokens (`passlib` + `python-jose`)
- **Document ingestion**: PDF, DOCX, TXT, Markdown -> text extraction -> chunking (with overlap) -> embeddings -> FAISS
- **Semantic search**: `/search` returns the most relevant chunks with similarity scores
- **Chat with citations**: `/chat` answers a question and always returns the source `filename` + `page`
- **Executive summarization**: `/documents/{id}/summary`
- **Requirements / action-item extraction**: `/documents/{id}/requirements`
- **Document management**: list / delete
- **Structured logging**: every request logged with method, path, status, latency
- **Config via `.env`**: nothing hardcoded
- **Pluggable embeddings**: `hash` backend works fully offline (deterministic, zero network calls) for demos/CI; switch to `sentence-transformers` for real semantic embeddings in production (one line in `.env`)
- **Graceful LLM fallback**: if `OPENAI_API_KEY` is empty, chat/summary/requirements still work using extractive methods instead of failing
- **Docker + docker-compose**
- **22 automated tests** covering auth, upload, chat, search, summary, requirements, access control, and per-user document isolation
- **Per-user document isolation**: uploads are tagged with their owner, and list/search/chat/summary/requirements/delete are all scoped to the requesting user
- **Swagger UI** at `/docs`

## Why the embedding fallback exists (an honest engineering note)

Real semantic embedding models (sentence-transformers) need to download
weights from the internet the first time they run. That's fine in a
normal deployment, but it means the app would silently break in an
offline demo, in CI, or in a network-restricted environment. Instead of
hiding that risk, `EMBEDDING_BACKEND=hash` is the default: a fast,
deterministic, dependency-free embedding that keeps the entire pipeline
(chunking -> embedding -> FAISS -> retrieval -> citations) fully
functional with zero external calls. Flip one setting in `.env` to use
real sentence-transformer embeddings once you have network access to
download the model. Same pattern applies to the LLM call: no API key ->
extractive answers instead of a crash.

## Running locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for interactive Swagger UI.

## Running with Docker

```bash
docker-compose up --build
```

## Running the tests

```bash
pytest app/tests/ -v
```

22 tests covering: registration/login/duplicate handling, JWT protection
on every endpoint, file upload + unsupported file rejection, document
listing/deletion, chat answers with sources, chat with an empty
knowledge base, semantic search ranking, summarization, requirement
extraction, and per-user document isolation.

## Running the live smoke test

Starts a real server, hits every endpoint end-to-end (register -> login
-> upload -> chat -> search -> summary -> requirements -> delete), and
shuts it down:

```bash
python scripts/smoke_test.py
```

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Create a user |
| POST | `/auth/login` | No | Get a JWT access token |
| POST | `/auth/logout` | Yes | Logout (client discards token) |
| GET | `/auth/me` | Yes | Current user info |
| POST | `/upload` | Yes | Upload + ingest a document (pdf/docx/txt/md) |
| POST | `/chat` | Yes | Ask a question, get an answer + sources |
| POST | `/search` | Yes | Semantic search over chunks |
| GET | `/documents` | Yes | List ingested documents |
| DELETE | `/documents/{doc_id}` | Yes | Remove a document from the index |
| GET | `/documents/{doc_id}/summary` | Yes | Executive summary |
| GET | `/documents/{doc_id}/requirements` | Yes | Extracted requirements / action items |
| GET | `/health` | No | Health check |

## Tech stack

Python, FastAPI, Pydantic, python-jose (JWT), passlib (sha256_crypt), FAISS,
PyMuPDF, python-docx, sentence-transformers (optional), OpenAI SDK
(optional), Docker, pytest.

## Future work

- Swap the JSON user store for PostgreSQL + SQLAlchemy
- Add role-based access control (admin vs engineer), since today isolation is per-user but there's no admin/shared-document concept
- Streaming responses for `/chat`
- Support for API doc / bug tracker connectors (Jira, Confluence) as additional document sources
- Rate limiting on `/auth/login` and `/auth/register` (currently no protection against credential brute-forcing)
- A CI pipeline (none exists yet -- tests currently only run locally/manually)
