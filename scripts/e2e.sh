#!/usr/bin/env bash
# Start the API (fake renderer/OCR, mock agent and classifier) and the web dev server on a fresh
# data dir, run the Playwright suite, then stop everything (including orphan next-server processes).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/services/api/.venv"
E2E_DATA="$(mktemp -d)"
PIDS=()

kill_orphans() {
  pkill -f "next-server" 2>/dev/null
  pkill -f "next dev" 2>/dev/null
  pkill -f "uvicorn hwai.main:app" 2>/dev/null
  sleep 1
}

cleanup() {
  for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill -- "-$p" 2>/dev/null; done
  kill_orphans
  rm -rf "$E2E_DATA"
}
trap cleanup EXIT INT TERM

kill_orphans

# Use a pre-installed Chromium when Playwright's own build is not downloaded.
if [ -z "${PW_CHROMIUM_PATH:-}" ]; then
  CAND="$(ls /opt/pw-browsers/chromium-*/chrome-linux64/chrome 2>/dev/null | head -1)"
  [ -n "$CAND" ] && export PW_CHROMIUM_PATH="$CAND"
fi

# Mocks are test-only switches (ignored when ENV=production). The classifier can be switched per
# request with the X-Test-Classifier header while CLASSIFIER=mock:* is on.
export ENV=dev RENDERER=fake OCR=fake AGENT=mock CLASSIFIER=mock:ok DATA_DIR="$E2E_DATA"
(cd "$ROOT/services/api" && "$VENV/bin/alembic" upgrade head >/dev/null) || exit 1

setsid bash -c "cd '$ROOT/services/api' && exec '$VENV/bin/uvicorn' hwai.main:app --app-dir src --port 8000" &
PIDS+=("$!")
setsid bash -c "cd '$ROOT/apps/web' && exec npm run dev" &
PIDS+=("$!")

for _ in $(seq 1 90); do
  curl -sf localhost:8000/health >/dev/null && curl -sf localhost:3000 >/dev/null && break
  sleep 1
done
curl -sf localhost:8000/health >/dev/null || { echo "API did not start"; exit 1; }
curl -sf localhost:3000 >/dev/null || { echo "web did not start"; exit 1; }

cd "$ROOT/apps/web" && npx playwright test "$@"
