# handwriting-ai

A web app that learns a person's handwriting from their own documents, then writes new text onto a file they upload (card, letter template, planner or notebook page) in that handwriting, with natural variation. Upload your own handwriting, open a chat, upload a target file, say what to write and where, preview, tweak in chat, export a PDF or PNG. English only for now.

Stack: FastAPI + SQLite (`services/api`), Next.js + Tailwind (`apps/web`). Needs Python 3.11+, Node 20+ and `make`.

## Install (one command)

```
make install
```

Installs the web packages, creates `services/api/.venv` and installs the API with its dev tools.

## Run (one command)

No API keys needed, with the fake renderer and OCR, a mocked chat agent and no payment:

```
ENV=dev DEV_USER=1 BILLING=off AGENT=mock RENDERER=fake OCR=fake make dev
```

API on http://localhost:8000 (`curl localhost:8000/health` answers `"status":"ok"`), web on http://localhost:3000. `DEV_USER=1` acts as a built-in dev user so you can skip signup. `make dev` first applies the database migrations. Data goes to `./data` (gitignored).

Try it: open http://localhost:3000/hand, tick the "own handwriting" box and upload a photo or PDF of your handwriting (for a quick test use `services/api/tests/fixtures/hand_page_1.png`). When it says ready, open Chats, start a chat, upload `services/api/tests/fixtures/card.pdf`, and type "write happy birthday". A preview appears; export as PDF or PNG.

With a real chat agent set `ANTHROPIC_API_KEY` and drop `AGENT=mock` (model: `AGENT_MODEL`, default `claude-haiku-5-5`). Without `DEV_USER=1` you sign up and log in; outside `ENV=dev` set `SECRET_KEY`.

## Fake or real renderer and OCR

| Variable | Values | Needs |
|---|---|---|
| `RENDERER` | `fake` (default: OFL handwriting font plus jitter, no GPU) or `onedm` | `make install-ml`, an NVIDIA GPU, `ONEDM_WEIGHTS_PATH` (and `ONEDM_VAE_PATH`) |
| `OCR` | `fake` (default, test fixtures only) or `trocr` | `make install-ml` (downloads `microsoft/trocr-base-handwritten`) |

```
make install-ml        # clones One-DM at the pinned commit into vendor/ and installs the ML extras
RENDERER=onedm OCR=trocr ONEDM_WEIGHTS_PATH=/path/One-DM-ckpt.pt make dev
```

`fake` OCR only understands the synthetic fixture page, so use `OCR=trocr` for real handwriting. See `CLAUDE.md` for the One-DM notes.

## Cost per page

On the GPU machine, with `make install-ml` done:

```
GPU_COST_THB_PER_HOUR=<your rental price in THB/h> ONEDM_WEIGHTS_PATH=/path/One-DM-ckpt.pt \
  services/api/.venv/bin/python scripts/measure_cost.py
```

Prints seconds and baht per rendered page and writes `data/cost_report.json`.

## Checks

```
make lint typecheck test e2e build audit
```

`make test` also enforces the coverage floor: at least 80% of statements in `hand/`, `page/`, `layout/`, `safety/` and `export.py` (`scripts/check_coverage.py`). `make e2e` starts its own servers with fake renderer/OCR and a mocked agent (set `PW_CHROMIUM_PATH` if Playwright's browser is not installed) and includes axe accessibility checks. `make audit` runs `pip-audit` and `npm audit --omit=dev` (needs network).

## Launch gate

Public One-DM weights were trained on research datasets. Before taking real money, retrain or fine-tune on data we have rights to. Payments in this pack stay in Stripe TEST mode. Never put live keys in the repo or `.env.example`.

## Billing (Stripe test mode only)

Price: 20 THB per document of up to 10 pages (`PRICING_MODE=per_document`), or 1 THB per page (`PRICING_MODE=per_page`). Checkout uses PromptPay in THB. For local work without Stripe, `BILLING=off` (honoured only with `ENV=dev`) skips payment.

To try the paid flow in test mode:

1. In the Stripe dashboard (test mode) enable PromptPay and copy the test secret key.
2. Set `STRIPE_SECRET_KEY=sk_test_...` (anything else fails startup), `SECRET_KEY=<random string>` and `BILLING=on`.
3. Forward webhooks: `stripe listen --forward-to localhost:8000/billing/webhook`, and set `STRIPE_WEBHOOK_SECRET=whsec_...` from its output.
4. Export a render: the API answers 402 `payment_required` with a checkout link; paying in the test dashboard marks it paid and unlocks that render version.

## Environment variables

Copy `.env.example` to `.env` (API) and `apps/web/.env.local` (web). Never commit real values.

| Variable | Purpose |
|---|---|
| `ENV` | `dev` enables `DEV_USER`, `BILLING=off`, `AGENT`/`CLASSIFIER` mocks and `GET /admin/cost`; anything else is production-like |
| `DEV_USER`, `BILLING` | dev switches described above |
| `DATA_DIR` | uploads, crops, renders, SQLite file (default `./data`) |
| `SECRET_KEY` | signs session cookies; required outside `ENV=dev` |
| `RENDERER`, `OCR` | `fake`/`onedm`, `fake`/`trocr` |
| `ANTHROPIC_API_KEY`, `AGENT_MODEL`, `AGENT` | chat agent (`AGENT=mock` for a key-free fixed placement) |
| `CLASSIFIER` | `real` or `mock:<kind>` (test switch, ignored in production) |
| `ONEDM_REPO_DIR`, `ONEDM_WEIGHTS_PATH`, `ONEDM_VAE_PATH`, `GPU_COST_THB_PER_HOUR` | One-DM GPU worker and cost script |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe TEST keys only |
| `PRICING_MODE`, `PRICE_THB_PER_DOCUMENT`, `PRICE_THB_PER_PAGE`, `MAX_PAGES_PER_DOCUMENT` | pricing |
| `NEXT_PUBLIC_API_BASE_URL` | where the web app finds the API (`apps/web/.env.local`) |

## Safety and privacy

Only your own handwriting (confirmed by a checkbox), no signatures, no cheques, contracts, legal or government forms, no school assignments or exams. Every export is marked AI generated (PDF metadata, PNG text chunk, visible footer). Delete your data with `DELETE /chats/{id}` (the chat, its files, renders and exports) and `DELETE /hand` (all samples, crops and documents).
