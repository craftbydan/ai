# Handwriting AI — CLAUDE.md

Working name: **handwriting-ai** (folder and project name).

## What this is
A web app that learns a person's handwriting from their own documents, then writes new text onto files they upload (card, letter template, planner or notebook page) in that handwriting, with natural variation so no two letters look identical.

Core loop: **upload your own handwriting → profile is built → open a chat, upload a target file, say what to write and where → preview → tweak in chat → export PDF/PNG.**

MVP is **English only**. Thai is a later, separate pack. Keep text handling behind a `TextSplitter` interface (see below) so a Thai splitter can plug in later without rewrites.

## Stack and why
- **Backend: Python 3.11+, FastAPI, SQLite (SQLAlchemy 2 + Alembic).** The handwriting models are PyTorch/Python, so the API and the model worker live in one language.
- **Frontend: Next.js (App Router), TypeScript, Tailwind CSS.** Mainstream, well documented, easy to type-check and test.
- **Handwriting generator: One-DM (MIT code)** behind a `Renderer` interface. A `FakeRenderer` (OFL handwriting font + jitter) is always available so everything is testable without a GPU.
- **Handwriting OCR: TrOCR** (`microsoft/trocr-base-handwritten` via Hugging Face `transformers`) behind an `OcrEngine` interface. A `FakeOcr` exists for tests.
- **Agent: Anthropic API (vision + tool use)** with a small, fast model set by `AGENT_MODEL` (default `claude-haiku-5-5`). Cost per page matters, so keep prompts short and images small.
- **PDF in/out: `pypdfium2` (render PDFs to images), `reportlab` + `pikepdf` (write PDFs and metadata), `Pillow`, `opencv-python-headless`.** Do NOT use PyMuPDF (AGPL).
- **Payments (last prompt only): Stripe in TEST mode** (PromptPay for THB).

Runner-up stack: a single Next.js app calling a hosted GPU API. It lost because the model code and OCR are Python, and one language for the pipeline is simpler.

## Folder structure
```
handwriting-ai/
  CLAUDE.md
  PROGRESS.md
  Makefile
  .env.example
  apps/web/                    # Next.js app
    src/app/                   # routes: /, /hand, /chats, /chats/[id], /login
    src/components/
    src/lib/api.ts             # typed client for the API
    tests/                     # vitest unit tests
    e2e/                       # playwright tests
  services/api/
    pyproject.toml
    alembic/
    src/hwai/
      main.py                  # FastAPI app factory
      config.py                # env settings (pydantic-settings)
      db.py, models.py, schemas.py
      routes/                  # health, auth, hand, chats, exports, billing
      storage.py               # local file storage under data/
      pdfio.py                 # PDF/PNG <-> image helpers
      text/splitter.py         # TextSplitter interface + EnglishSplitter
      render/                  # base.py (Renderer), fake.py, onedm.py, jitter.py
      hand/                    # ingest.py, ocr.py, segment.py, profile.py
      page/                    # analyze.py (lines, boxes, blank areas), regions.py
      layout/                  # place.py (words -> pixels on a region)
      agent/                   # loop.py, tools.py, prompts.py
      safety/                  # rules.py, signature.py, classify.py
      export.py                # flatten + AI-generated marking
      billing.py
    tests/
      fixtures/                # synthetic handwriting pages, sample card/planner PDFs, OFL font
  data/                        # gitignored: uploads, crops, renders, sqlite file
  scripts/
    measure_cost.py            # seconds and baht per rendered page
```

## Data model (SQLite)
- `users(id, email, password_hash, created_at)`
- `hands(id, user_id, status[empty|learning|ready|failed], own_hand_confirmed_at, created_at)`
- `hand_documents(id, hand_id, file_path, page_count, status, created_at)`
- `word_samples(id, hand_id, document_id, text, crop_path, width, height, ocr_confidence, quality_score)`
- `chats(id, user_id, hand_id, title, created_at)`
- `chat_files(id, chat_id, file_path, kind[pdf|image], page_count, analysis_json, safety_status[ok|refused], safety_reason)`
- `messages(id, chat_id, role[user|assistant|tool], content_json, created_at)`
- `renders(id, chat_id, version, placements_json, preview_path, created_at)`
- `exports(id, render_id, format[pdf|png], file_path, created_at)`
- `payments(id, user_id, chat_id, stripe_session_id, status, amount_thb, pages, created_at)`  *(last prompt)*
Access rule: every row is reachable only by its owning user. Every route checks ownership.

## Key interfaces (do not change names; later prompts rely on them)
- `Renderer.render_word(word: str, style_refs: list[StyleRef], seed: int, size_px: int) -> WordImage` (RGBA PNG on transparent background, plus baseline offset).
- `OcrEngine.read_line(image) -> OcrResult(text, confidence)`.
- `TextSplitter.units(text: str) -> list[str]` — English: words and punctuation units.
- `Region(id, page, kind[line|box|blank], bbox_px, baseline_px|None, line_height_px|None)`.
- `Placement(region_id, text, align[left|center|right], size_scale, slant_deg, jitter, seed)`.

## Commands (run from repo root unless noted)
- Install: `make install`  (runs `npm install` in `apps/web`, creates `services/api/.venv`, `pip install -e ".[dev]"`)
- Install ML extras (GPU/heavy, optional): `make install-ml`
- Dev servers: `make dev`  (API on http://localhost:8000, web on http://localhost:3000)
- Build: `make build`  (`next build` and a Python import check)
- Type-check: `make typecheck`  (`tsc --noEmit` and `mypy src`)
- Lint: `make lint`  (`eslint` and `ruff check` + `ruff format --check`)
- Test: `make test`  (`pytest` in `services/api`, `vitest run` in `apps/web`)
- E2E: `make e2e`  (Playwright against dev servers using FakeRenderer, FakeOcr and a mocked agent)
- DB migrate: `make migrate`
All of these must exist and pass after Prompt 1.

## Conventions
- Python: type hints everywhere, `ruff` clean, `mypy` clean, pydantic models for every API body. Pure functions for image math so they unit-test without a GPU.
- TypeScript: strict mode, no `any`, API types come from one file `src/lib/api.ts`.
- Names: snake_case Python, camelCase TS, kebab-case routes. JSON fields snake_case across the API.
- Errors: API returns `{ "error": { "code": str, "message": str } }` with a correct HTTP status. UI shows the message, never a stack trace.
- Tests: every prompt that adds behaviour adds tests. Image tests use synthetic fixtures generated from an OFL handwriting font with known text, never real people's handwriting.
- Heavy models are never imported at module top level; import inside the function that uses them so `make test` works without torch.
- Config only through env vars in `config.py`; secrets never logged and never committed.
- Page coordinates: pixels at 150 DPI for analysis, top-left origin. Convert to PDF points only inside `export.py`.

## Use / Avoid
Use:
- One-DM — https://github.com/dailenson/One-DM (MIT, ECCV 2024, one-shot handwriting generation). Pin to a commit hash after cloning and record it here. Read its README for the real inference entry point; do not guess its API.
- `transformers` + TrOCR for handwriting OCR; `opencv-python-headless`, `Pillow`, `numpy`, `pypdfium2`, `reportlab`, `pikepdf`.
- `anthropic` Python SDK for the agent.
- `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `pydantic-settings`, `pytest`, `httpx`, `ruff`, `mypy`.
- `next`, `react`, `tailwindcss`, `vitest`, `@playwright/test`, `eslint`.
- Record the exact resolved versions of every dependency in this file under "Resolved versions" after Prompt 1 and Prompt 4.
Avoid:
- PyMuPDF/fitz (AGPL). Any repo with no license. Any library with no commit in about 18 months.
- DiffInk weights (research-only). Using One-DM public weights for paid output without retraining on data you have rights to (see Launch gate).
- Cloud OCR or cloud handwriting APIs; keep ink and documents local to the app.

## Safety rules (enforced in code and tests, not just prompts)
1. Train only on the user's own handwriting, confirmed by a checkbox at upload, stored as `own_hand_confirmed_at`.
2. Block signatures and anything that looks like one: no signature-style output, no placing text on a "signature" line.
3. Refuse cheques, contracts, legal or government forms.
4. Refuse school assignments, worksheets and exams.
5. Mark every exported file as AI generated (PDF metadata, PNG text chunk, and a small visible footer mark).
Refusals are friendly, say why, and are logged on `chat_files.safety_reason`.

## Launch gate
Public One-DM weights were trained on research datasets. Before taking real money, retrain or fine-tune on data we have rights to. Payments in this pack stay in Stripe TEST mode. Never put live keys in the repo or `.env.example`.

## Pricing (for the billing prompt)
Launch: 20 THB per document of up to 10 pages. Later: 1 THB per page. Price lives in `config.py` (`PRICE_THB_PER_DOCUMENT=20`, `MAX_PAGES_PER_DOCUMENT=10`). Cost per page is measured by `scripts/measure_cost.py`; at 1 THB a page the margin is thin, so rendering must stay cheap.

## Don'ts
- Don't build Thai support, per-user fine-tuning, SVG pen-plotter export or a mobile app in this pack.
- Don't add features from later prompts early. Don't swap pinned libraries.
- Don't commit data/, weights, `.env`, or any uploaded document.
- Don't fake model output in production code paths; fakes live only in `render/fake.py`, `hand/ocr.py::FakeOcr` and test fixtures, and are chosen by env flags `RENDERER=fake|onedm` and `OCR=fake|trocr`.

## Resolved versions
Recorded after Prompt 1 (installed 2026-11-17; Python 3.13.18, Node v22.23.4, npm 10.9.9).

API (`services/api`, pip, latest at install time; `ml` extra not installed):
fastapi 0.163.1, uvicorn 0.54.0, SQLAlchemy 2.1.9, alembic 1.20.1, pydantic 2.14.3, pydantic-settings 2.16.3, python-multipart 0.0.34, Pillow 13.0.0, numpy 2.5.5, opencv-python-headless 5.0.0.93, pypdfium2 5.15.2, reportlab 5.1.0, pikepdf 10.18.2, pytest 9.2.0, httpx 0.28.1, ruff 0.17.5, mypy 2.4.1.

Web (`apps/web`, npm):
next 16.4.6, react 19.3.1, react-dom 19.3.1, typescript 6.0.3, tailwindcss 4.3.5, @tailwindcss/postcss 4.3.5, postcss 8.5.33, vitest 5.1.0, @playwright/test 1.65.1, eslint 9.39.5, eslint-config-next 16.4.6, @types/node 26.6.6, @types/react 19.3.0, @types/react-dom 19.3.0.

Fixture font: Caveat (variable font `Caveat[wght].ttf`, saved as `services/api/tests/fixtures/Caveat.ttf`, downloaded from github.com/google/fonts/ofl/caveat), licence in `fixtures/OFL.txt` (SIL OFL 1.1).

Notes: `make dev` and `make migrate` set `DATA_DIR` to `<repo>/data`. If Playwright's bundled browser is not installed, set `PW_CHROMIUM_PATH` to a Chromium binary before `make e2e`.
