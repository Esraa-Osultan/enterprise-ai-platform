# Engineering Audit — Addendum (Architecture_criteria.txt pass)

**Scope of this pass:** the first audit (`AUDIT_REPORT.md`) was mostly a security pass.
This addendum applies the rest of `Architecture_criteria.txt` — architecture consistency,
API contract review, AI/RAG review, deployment review, and test quality review — that the
first pass didn't systematically cover. Same constraints as before: **no network access,
no dependencies installable, nothing executed.** Every claim below is from reading the
code, not from running it. `python -m py_compile` passed on every file touched; that
proves syntax only.

---

## 1. Architecture consistency

**1.1 — Encapsulation break in `DocumentService.get_full_text` (`app/services/document_service.py`)**
Every other read path (`search`, `list_documents`, `delete_document`) is a method on
`VectorStore`. `get_full_text` was the one exception: it reached directly into
`self.vector_store.metadata` — a list `VectorStore` otherwise treats as its own —
filtering it from outside the class that owns it. Not a bug (the filter logic was
correct), but a real coupling problem: any future change to how `VectorStore` stores
records (e.g. an actual DB) would silently break this one call site because it wasn't
going through the class's interface.
**Fixed:** added `VectorStore.get_chunks(doc_id, owner)`; `document_service.py` now calls
it instead of touching `.metadata`.

## 2. API contract review

**2.1 — Inconsistent response contracts (`app/api/documents.py`, `app/api/search.py`, `app/api/upload.py`)**
`app/api/chat.py` declared a `response_model` (`ChatResponse`) from the start, so it gets
schema validation, a typed OpenAPI entry, and a guarantee that a service-layer change
can't silently reshape what the client receives. Every other router — `/documents`,
`/documents/{id}` DELETE, `/documents/{id}/summary`, `/documents/{id}/requirements`,
`/search`, `/upload` — returned bare dicts with no `response_model` at all. That's the
kind of inconsistency `Architecture_criteria.txt` explicitly asks to catch: "No endpoint
should return inconsistent responses" is as much about *declared* contracts as accidental
ones.
**Fixed:** added `DocumentListResponse`, `DeleteResponse`, `SummaryResponse`,
`RequirementsResponse`, `SearchResponse`, and `UploadResponse` Pydantic models; every
route in the app now has a `response_model`. Error responses were already consistent
(FastAPI's default `{"detail": ...}` shape via `HTTPException` everywhere) — that part
didn't need a fix.

## 3. AI / RAG review

**3.1 — Chunker could split a word across a chunk boundary (`app/rag/chunker.py`)**
`chunk_pages` sliced text by raw character offset (`text[start:end]`), with no awareness
of word boundaries. Since the default (and only offline) embedding backend
(`_embed_with_hash` in `app/rag/embeddings.py`) tokenizes by `text.lower().split()`, a
boundary landing mid-word turns one real token into two garbage half-tokens — neither of
which matches the original word in a query. The 120-character overlap means the *whole*
word usually appears intact in the neighboring chunk too, so this was a quality
degradation, not a correctness bug, and only affects the chunk(s) where the cut actually
lands mid-word.
**Fixed:** added `_extend_to_word_boundary`, which nudges a non-final chunk boundary
forward to the next whitespace (capped at a 40-character lookahead so one abnormally long
token, e.g. a URL, can't blow out the chunk size). Verified by reading, not executed —
worth a real pytest assertion (e.g. "no chunk boundary lands inside a token that appears
whole in the source text") if/when the suite can run.

**3.2 — Noted, not changed: no context-length truncation in `pipeline.py`'s LLM path**
`app/services/analysis_service.py` truncates to `full_text[:12000]` before calling the
LLM; `app/rag/pipeline.py`'s `_generate_with_llm` builds its context by joining *all*
retrieved sources with no cap. At the shipped defaults (`top_k=4`, `chunk_size=800`) the
max context is ~3.2K characters, so this isn't a live bug — but it's a latent one:
raising `top_k` or `chunk_size` in `.env` (both are meant to be tunable, per their own
docstrings) has no upper bound protecting the LLM call from an oversized prompt. Not
fixed — the two callers should share one truncation policy rather than each inventing
its own number, and picking that shared number (and whether it's chars or tokens) is a
product decision, not something to guess at silently.

## 4. Deployment review

**4.1 — No `HEALTHCHECK` in the Docker image despite a `/health` endpoint existing**
The image exposed `/health` but nothing in the `Dockerfile` used it, so an orchestrator
(compose, Kubernetes, ECS) had no way to detect a hung-but-still-listening process.
**Fixed:** added a `HEALTHCHECK` that curls `/health` via `urllib` (no extra dependency).

**4.2 — Image ran as root**
No `USER` directive anywhere in the original `Dockerfile`. A container escape or an RCE
in any dependency (FAISS, PyMuPDF, etc. all parse untrusted user-uploaded files) would
get root inside the container for free.
**Fixed:** added a dedicated `app` system user/group; the final stage runs as `app`, not
root.

**4.3 — Default JWT secret baked into every built image**
`COPY .env.example ./.env` copied `JWT_SECRET_KEY=change-this-secret-in-production`
straight into the image. Anyone deploying the image as-built (without also mounting or
overriding `.env`) ships with a publicly-known, forgeable JWT secret — silently, since
the app starts up fine either way.
**Fixed:** the `Dockerfile` no longer copies any `.env` file at all. Configuration comes
from the runtime environment (`env_file`/`environment` in `docker-compose.yml`, or `-e`
flags), which is how `docker-compose.yml` was already configured to supply it — so this
is a strict tightening, not a behavior change for anyone already using `docker-compose up`.

**4.4 — No image-size optimization / build tooling shipped in the runtime image**
The whole build (`build-essential` + all of `requirements.txt`, including compiling
`faiss`/`PyMuPDF` wheels) happened in one stage that was also the final image, so
`build-essential` and pip's build cache shipped in the runtime image with no purpose
after the wheels were built.
**Fixed:** split into a `builder` stage (installs to `--user`, has `build-essential`) and
a `runtime` stage that only copies the installed site-packages and the `app/` source.

**4.5 — No `.dockerignore`**
Without one, `docker build` sends the whole repo as build context, including `data/`
(uploads, the vector store, `users.json` if it exists locally), `.git/`, and `venv/` —
none of which belong in an image and some of which (`data/users.json`, `.env`) are
exactly the kind of thing you don't want accidentally baked into a layer if someone later
adds a stray `COPY . .`.
**Fixed:** added `.dockerignore` excluding `data/`, `.git/`, `venv/`/`.venv/`, `.env`,
tests, docs, and caches.

**4.6 — Not independently re-verified this pass:** startup speed, graceful shutdown
behavior beyond FastAPI's default `lifespan` handling, and log rotation (`RotatingFileHandler`
in `app/core/logging_config.py`) were already reviewed in the first pass and nothing in
this pass changed them.

## 5. Test quality review

**5.1 — The path-traversal and file-size fixes from the first audit pass had zero test
coverage.** `AUDIT_REPORT.md` items 1.2 and 1.5 fixed real vulnerabilities but, unlike
item 1.1 (which got `test_isolation.py`), shipped with no regression test — so a future
refactor of `upload.py` could silently reintroduce either bug with nothing to catch it.
**Fixed:** added to `app/tests/test_upload.py`:
- `test_upload_path_traversal_filename_is_sanitized` — asserts a `"../../evil.txt"`
  filename never gets written outside the upload dir and the client-supplied name is
  preserved only for display.
- `test_upload_rejects_files_over_size_limit` — monkeypatches `MAX_UPLOAD_BYTES` down so
  the test doesn't need to actually send 25MB, asserts a 413 and that no partial file is
  left on disk.
- `test_upload_empty_file_returns_422` — a whitespace-only file should fail cleanly, not
  produce a phantom zero-chunk document.

**5.2 — Missing validation-failure and empty-state edge cases.** The original suite
tested the happy path for register/login and one empty-knowledge-base case for `/chat`,
but not: invalid email format, too-short password, login against a username that was
never registered, `/search` against an empty index, or `/documents/{id}/summary` for an
id that doesn't exist. These are exactly the "missing edge cases" and "missing
failure-path tests" the criteria calls out.
**Fixed:** added `test_register_invalid_email_rejected`, `test_register_short_password_rejected`,
`test_login_nonexistent_user_fails` (`test_auth.py`), and
`test_search_with_no_documents_returns_empty_results`,
`test_summary_for_nonexistent_document_returns_404` (`test_chat.py`).

**Test count: 22 → 30.** As before: **I did not run these.** They're written in the same
style/fixtures as the existing suite and pass `py_compile`, but that only proves syntax.

## 6. What I looked at and left alone (Python review, further security review)

- Typing, dataclass usage (`Chunk`, `PageText`, `User`), `pathlib`-vs-`os.path` usage, and
  the exception hierarchy (`UnsupportedFileType`, `ValueError` for 422s) were already
  reasonable and consistent across the codebase; no changes made there.
- Re-checked for SQL injection, insecure deserialization, and command injection: no SQL
  in this codebase (JSON-file stores only), no `pickle`/`eval`/`subprocess` anywhere.
  Nothing found beyond what the first pass already covered.
- Did not touch the three "Low / not changed" items from the first report (default JWT
  secret *value*, `sha256_crypt` choice, no rate limiting) — they're policy/ops decisions
  the first report correctly declined to make unilaterally, and nothing in this pass
  changes that judgment.

## 7. Bottom line

This pass fixes real inconsistencies (unencapsulated internals, non-uniform API
contracts), a real quality gap in chunking, closes two test-coverage holes left by the
previous security fixes, adds four new edge-case tests, and hardens the Docker image on
four separate axes (root user, no healthcheck, baked-in secret, bloated image). None of
this changes the conclusion of the first report: this is **still not fully
production-ready** — no CI, no rate limiting, single-process-only JSON "database," and
(now at least not image-baked, but still default-value) JWT secret handling are unchanged
gaps. Nothing in this pass was run; it needs execution in an environment with network
access before either report's claims should be trusted at the "passes" level rather than
the "reads correctly" level.
