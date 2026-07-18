# Engineering Audit — enterprise-ai-platform

**Method:** full manual read of every source file (25 Python files, ~1,360 lines), plus
targeted greps for dead code, dependency usage, and secrets. **No dependencies could be
installed and no code could be executed** — this sandbox has no network access, `pip
install` fails on every package, and none of fastapi/pydantic/faiss/etc. are pre-installed.
So: **nothing in this report claims "ran and passed."** Where I couldn't execute something,
I say so explicitly. The only thing I actually *ran* was `python -m py_compile` on every
file I edited, which only proves valid syntax, not correct behavior.

If you want the tests/Docker build actually executed, that has to happen in an environment
with internet access (locally, CI, or a sandboxed environment with egress enabled).

---

## 1. Issues found, by severity

### High

**1.1 — No per-user document isolation (`app/rag/vector_store.py`, `app/services/document_service.py`, `app/api/documents.py`, `app/api/chat.py`, `app/api/search.py`)**
All authenticated users shared one FAISS index with no owner field. Any logged-in user
could list, search, chat over, summarize, extract requirements from, and **delete** any
other user's uploaded documents — just by knowing (or brute-forcing, since `doc_id`s
are visible in the shared `/documents` list before the fix) another user's `doc_id`. For
a platform explicitly pitched as "Enterprise," this is the most significant gap: it means
Engineer A's confidential spec is readable and deletable by Engineer B the moment both
have accounts. The README itself listed "per-user document namespaces" under *Future
work*, so this wasn't a documentation gap — it was a known, disclosed limitation.
**Fixed:** every record now carries an `owner`; list/search/chat/summary/requirements/delete
all filter by `owner=current_user.username` (see `1.4` for the corresponding test
coverage that didn't exist before).

**1.2 — Path traversal / arbitrary file write via upload filename (`app/api/upload.py`)**
```python
dest_path = os.path.join(settings.upload_dir, file.filename)
```
`file.filename` is a client-controlled multipart header with zero sanitization. A
filename like `../../app/main.py` or `..%2f..%2fapp/main.py` writes outside
`data/uploads/`. Combined with `.txt`/`.md` being allowed extensions, this is a real
arbitrary-file-write primitive (limited by what a `.txt`/`.md`/`.pdf`/`.docx`-suffixed
path can overwrite, but still).
**Fixed:** the original filename is kept only for display; the file is always written to
a server-generated `uuid4().hex + ext` name under `upload_dir`, via `os.path.basename()`
plus a fixed extension whitelist.

### Medium

**1.3 — `UserStore` race condition on registration (`app/models/user.py`, `app/auth/dependencies.py`)**
`UserStore.create()` takes a `threading.Lock()` before its read-check-write, which looks
correct in isolation — but the old `get_user_store()` returned a **new `UserStore`
instance (and therefore a new, uncontended lock) on every request**. Two concurrent
`/auth/register` calls for the same not-yet-existing username could both pass the
`exists()` check before either write landed, and the second write silently overwrites the
first (last-write-wins JSON dump) — one of the two accounts is lost with no error to
either client.
**Fixed:** `get_user_store()` is now `@lru_cache`d (mirroring the pattern already used
correctly for `VectorStore`/`DocumentService` in `app/api/deps.py`), so the lock is
actually shared. Note this still only fixes it within one process — with multiple
uvicorn workers the JSON file itself has no cross-process locking; that's a real
limitation of "JSON file as a database" that only goes away by swapping to a real DB, as
the README's future-work section already flags.

**1.4 — Missing test coverage for the exact bug in 1.1**
Before this audit there were 18 tests and **none** exercised cross-user access. Nothing
asserted that user B is blocked from another user's documents, so the isolation gap in
1.1 shipped without a single failing test to catch it.
**Fixed:** added `app/tests/test_isolation.py` (4 tests: list-scoping, delete-blocking,
summary-blocking, search-scoping). Total is now 22 tests. **I have not executed these** —
see the top of this report. They're written to the same style/fixtures as the existing
suite and pass `py_compile`, but "compiles" and "passes" are different claims.

**1.5 — No file size limit on `/upload`**
The original handler streamed the request body straight to disk with no cap — a large
upload could fill the disk or exhaust memory depending on how the ASGI server buffers it.
**Fixed:** added a 25 MB ceiling, enforced while streaming (not after the fact), with the
partial file cleaned up on rejection.

**1.6 — Uploaded files were kept on disk indefinitely, serving no purpose**
Once ingested, chunk text lives in the FAISS metadata; nothing ever reads the original
file back from `data/uploads/`. The old code left it there forever (a slow, unbounded
disk leak, and one more copy of potentially sensitive content sitting around outside the
access-controlled API). **Fixed:** the temp file is now deleted right after ingestion
(success or failure) in `app/api/upload.py`.

**1.7 — Dead code: `app/models/document.py` (`DocumentMeta`)**
Defined, never imported or instantiated anywhere (confirmed via repo-wide grep).
`vector_store.list_documents()` builds its own plain dicts instead. **Fixed:** removed
the file. If you want a dataclass wrapping document metadata again, `VectorStore` is
where it'd actually need to plug in.

**1.8 — Documentation didn't match implementation (`README.md`)**
Tech-stack section claimed `passlib (bcrypt)`; the code uses
`CryptContext(schemes=["sha256_crypt"])`. Also claimed "18 tests, all passing" — a claim
about test *execution* the README's author couldn't have verified any more than I could
in an offline sandbox review; I've reworded it to describe what the tests cover without
asserting a run result I haven't produced. **Fixed both.**

### Low / worth knowing about, not changed

- **JWT secret has a public, guessable default** (`change-this-secret-in-production` in
  `app/core/config.py`). If a deployment forgets to set `JWT_SECRET_KEY`, tokens are
  forgeable by anyone who's read this repo (which, once public on GitHub, is anyone).
  Not fixed — there's no code fix that helps here beyond what already exists (the
  setting is externalized and documented); the actual fix is operational (secrets
  management in the real deployment), which is out of scope for a code change.
- **No rate limiting on `/auth/login` or `/auth/register`** — brute-forceable. Already
  called out in the README's future work; a real fix means picking and wiring a limiter
  (e.g. `slowapi`), which needs a dependency addition and design decision (per-IP? per-
  account?) I didn't feel entitled to make unilaterally in this pass.
- **No CI pipeline exists** (no `.github/workflows/`, nothing else that runs tests on
  push). The audit brief asked me to verify CI; there is none to verify. Adding one
  would also need to be written to run without network for the `hash` embedding
  backend, or provisioned with network for `sentence-transformers`/model downloads.
- **`docker/` folder was empty** and unreferenced beyond the README file listing.
  Removed the empty directory; nothing depended on it.
- **No CORS middleware** — fine if this is only ever called server-to-server or via
  Swagger, but if a browser-based frontend is planned, this will need explicit origins
  configured.
- **Password minimum length is 6** (`RegisterRequest.password: Field(min_length=6)`) —
  weak by modern standards but a policy choice, not a bug; flagging for awareness.
- **`sha256_crypt` instead of `bcrypt`/`argon2`** for password hashing. It's a real,
  non-broken algorithm (not the same class of problem as MD5/SHA1-for-passwords), just
  not the current best-practice default. I did not swap it, because that's a security-
  relevant behavior change (differing cost factors, differing dependency requirements)
  that deserves an explicit decision from you rather than a silent audit-driven swap.

## 2. What I verified was **not** a problem

- `.gitignore` correctly excludes `venv/`, `data/uploads/*`, `data/vector_store/*`,
  `data/users.json`, `data/app.log`, `__pycache__/` — confirmed via `git ls-files` that
  none of these are actually tracked in the repo's git history. No secrets or user data
  are committed.
- `.env` in the upload contains only placeholder values (no live API keys or a real JWT
  secret) — safe as shipped.
- The FAISS/embeddings/chunking pipeline is logically sound for what it claims to be: a
  deterministic, dependency-free "hash" embedding as the default with a documented
  swap to `sentence-transformers`, and an honest extractive fallback when no LLM key is
  set (rather than pretending to call an LLM). This is a good example of "fail
  gracefully and say so" and I'd leave it as-is.
- Every route requiring auth actually depends on `get_current_user` — I checked each of
  `chat`, `search`, `upload`, `documents` (all 4 sub-routes), and confirmed none of them
  skip the dependency.

## 3. What's still a future-work item (unchanged from README, still accurate)

- Swap `users.json` for a real database — needed for real concurrency (multi-process/
  multi-replica), which the in-process lock fix in 1.3 does not solve.
- RBAC (admin vs. regular user / shared documents) — right now isolation is strictly
  per-user with no concept of a shared or admin-visible document.
- Rate limiting on auth endpoints.
- A CI pipeline.

## 4. Why this is closer to production-ready than before, and where it still isn't

The single most important gap — documents leaking across users — is fixed and tested.
Path traversal on upload is fixed. The one real (if narrow) concurrency bug I found is
fixed. Dead code and a doc/code mismatch are cleaned up.

It is **not** fully production-ready as-is: no CI, no rate limiting, a single-process-only
JSON "database," and a hardcoded-default JWT secret that depends on the operator
remembering to override it are all real gaps for a genuine enterprise deployment, not
just cosmetic ones. I'd treat this as "solid internal demo / pilot," not "ready to put in
front of paying enterprise customers with sensitive data," until those four are addressed.

I could not run the test suite, build the Docker image, or start the server in this
environment — if that verification matters before you rely on this, it needs to happen
somewhere with network access.
