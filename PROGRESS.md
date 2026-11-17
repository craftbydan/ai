# Build progress — handwriting-ai

| # | Prompt | Status | Commit | Notes |
|---|--------|--------|--------|-------|
| 0 | CLAUDE.md | done | | pack files committed |
| 1 | Project setup and tooling | done | b6dd600 | make dev parent ignores SIGTERM (dev ergonomics only) |
| 2 | Data model, accounts-lite, uploads | done | 7104cea | |
| 3 | Renderer interface, fake, jitter, export | done | f230798 | |
| 4 | One-DM renderer and cost measurement | blocked (GPU) | ffb33f3 | CPU-side code and tests pass independent check; GPU criteria unverified |
| 5 | Learn the hand | done | 65191c2 | OCR=trocr run skipped (no torch) |
| 6 | Read the target page | done | 05ba5f3 | margin-line bug found by checker, fixed + tested |
| 7 | Layout engine | done | 25e6041 | |
| 8 | Chat agent | pending | | |
| 9 | Safety rules | pending | | |
| 10 | Web app | pending | | |
| 11 | Accounts and billing (test mode) | pending | | needs Stripe test keys |
| 12 | Testing and hardening | pending | | |

## What exists now
API: FastAPI app factory, GET /health, standard error shape, config, SQLite+Alembic (empty migration). Web: Next.js home page + src/lib/api.ts. Fixtures in services/api/tests/fixtures (Caveat font, hand_page_1.png/.json, card.pdf, planner.pdf, blank.png). Makefile targets all exist.

Prompt 2 adds: tables+migration 0002 (no payments), storage.py, pdfio (page_images, inspect_file), auth.py current_user() dev stub, errors.ApiError, routes /hand, /hand/documents, /chats, /chats/{id}, /chats/{id}/files, get_owned_chat helper, per-test DATA_DIR in conftest.

Prompt 3 adds: render/base.py (StyleRef, WordImage, Renderer), render/fake.py (+CLI), render/jitter.py, get_renderer() (onedm raises NotImplementedError until P4), text/splitter.py, export.py (export_png, export_pdf, mandatory AI marking, +CLI), bundled Caveat in render/assets.

Prompt 4 adds: render/onedm.py (OneDMRenderer, render_words, converters), make install-ml, scripts/measure_cost.py, pinned One-DM commit dde2205a.

Prompt 5 adds: hand/ocr.py (OcrEngine, FakeOcr, TrocrOcr, get_ocr), hand/segment.py (BBox, find_lines, split_words, deskew_page), hand/ingest.py (background job), hand/profile.py (rebuild_profile, style_refs_for(hand_id, k, seed, db=None)), migration 0003 (hands.status_reason), GET /hand now has status_reason, status_message, sample_count; db.new_session().

Prompt 6 adds: page/analyze.py (analyze_page, draw_regions, CLI), page/regions.py (Region), analysis_json on chat files, GET /chats/{id}/files/{fid}/analysis and /pages/{n}.png.

Prompt 7 adds: layout/place.py (layout_text, compose, PlacedText), Placement/RenderRequest/FitReport/RenderOut schemas, routes/renders.py (POST /chats/{id}/render, GET .../renders/{v}/preview.png[?page=N]), routes/exports.py (POST /chats/{id}/export?version&format[&page]), storage.write_file, pdfio.pdf_page_size_points, export.image_size_points, 422 messages now name the bad field.

## Waiting on you
- Prompt 4: NVIDIA GPU machine, ONEDM_WEIGHTS_PATH, GPU_COST_THB_PER_HOUR
- Prompt 8: ANTHROPIC_API_KEY (live runs only)
- Prompt 11: SECRET_KEY, STRIPE_SECRET_KEY (sk_test_), STRIPE_WEBHOOK_SECRET

## Deviations
- P7: render uses the chat's latest uploaded file; composed pages are stored (page 1 = preview_path, others `-pN.png`) and export reads them, so exports match previews even if the hand changes; PDF export uses the original PDF's point size (images: 150 DPI conversion in export.py); render works regardless of hand status (agent will gate later); words rendered once at full size then shrunk by resize.
- P5: deskew is a separate deskew_page() called by ingest (boxes must be in the deskewed frame); split_words takes optional n_words (cut at widest gaps) used when OCR word count differs from threshold split; FakeOcr serves hand_page_1.json lines in order per page (override path with FAKE_OCR_TRUTH_PATH); profile prunes unselected samples (max 150, 4 per word); added hands.status_reason; test_uploads file counter now ignores crops/.
- P4 GPU risks (checker review, untested): data/unifont.pickle must be fetched from One-DM dataset into vendor/One-DM/data/; Laplace recipe is a guess; ml extras unpinned vs One-DM's py3.8/torch1.13.1/diffusers0.18.2; unet.eval() should be called before each sample; sampling is not behind a lock; one style ref per call.
- P3: StyleRef is a frozen dataclass (text, image); export_png overlay layers are (RGBA image, (x,y)) tuples; export.py imports FONT_PATH from render/fake.py.
- P2: added ENV setting and error codes own_hand_not_confirmed, file_too_large, too_many_pages; POST /chats creates an empty hand if none.
- P1: optional PW_CHROMIUM_PATH env in playwright.config.ts (bundled browser path missing); extra e2e smoke spec; python-multipart added to API deps.

Prompt 4 adds (no GPU run yet): render/onedm.py (OneDMRenderer, render_words, pure prepare_style/gray_to_rgba), render/fixture_style.py, get_renderer() -> OneDMRenderer, demo CLI honours RENDERER (+ --style), scripts/measure_cost.py, `gpu` pytest marker, config ONEDM_VAE_PATH / ONEDM_SAMPLING_STEPS / ONEDM_BATCH_SIZE, ML extras in pyproject.
