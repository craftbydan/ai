# Build progress — handwriting-ai

| # | Prompt | Status | Commit | Notes |
|---|--------|--------|--------|-------|
| 0 | CLAUDE.md | done | | pack files committed |
| 1 | Project setup and tooling | done | b6dd600 | make dev parent ignores SIGTERM (dev ergonomics only) |
| 2 | Data model, accounts-lite, uploads | done | 7104cea | |
| 3 | Renderer interface, fake, jitter, export | done | f230798 | |
| 4 | One-DM renderer and cost measurement | pending | | needs GPU |
| 5 | Learn the hand | pending | | |
| 6 | Read the target page | pending | | |
| 7 | Layout engine | pending | | |
| 8 | Chat agent | pending | | |
| 9 | Safety rules | pending | | |
| 10 | Web app | pending | | |
| 11 | Accounts and billing (test mode) | pending | | needs Stripe test keys |
| 12 | Testing and hardening | pending | | |

## What exists now
API: FastAPI app factory, GET /health, standard error shape, config, SQLite+Alembic (empty migration). Web: Next.js home page + src/lib/api.ts. Fixtures in services/api/tests/fixtures (Caveat font, hand_page_1.png/.json, card.pdf, planner.pdf, blank.png). Makefile targets all exist.

Prompt 2 adds: tables+migration 0002 (no payments), storage.py, pdfio (page_images, inspect_file), auth.py current_user() dev stub, errors.ApiError, routes /hand, /hand/documents, /chats, /chats/{id}, /chats/{id}/files, get_owned_chat helper, per-test DATA_DIR in conftest.

Prompt 3 adds: render/base.py (StyleRef, WordImage, Renderer), render/fake.py (+CLI), render/jitter.py, get_renderer() (onedm raises NotImplementedError until P4), text/splitter.py, export.py (export_png, export_pdf, mandatory AI marking, +CLI), bundled Caveat in render/assets.

## Waiting on you
- Prompt 4: NVIDIA GPU machine, ONEDM_WEIGHTS_PATH, GPU_COST_THB_PER_HOUR
- Prompt 8: ANTHROPIC_API_KEY (live runs only)
- Prompt 11: SECRET_KEY, STRIPE_SECRET_KEY (sk_test_), STRIPE_WEBHOOK_SECRET

## Deviations
- P3: StyleRef is a frozen dataclass (text, image); export_png overlay layers are (RGBA image, (x,y)) tuples; export.py imports FONT_PATH from render/fake.py.
- P2: added ENV setting and error codes own_hand_not_confirmed, file_too_large, too_many_pages; POST /chats creates an empty hand if none.
- P1: optional PW_CHROMIUM_PATH env in playwright.config.ts (bundled browser path missing); extra e2e smoke spec; python-multipart added to API deps.
