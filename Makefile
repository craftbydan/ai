export DATA_DIR ?= $(CURDIR)/data
API_DIR := services/api
WEB_DIR := apps/web
VENV := $(abspath $(API_DIR)/.venv)
PY := $(VENV)/bin/python

.PHONY: install install-ml dev build typecheck lint test e2e migrate

install:
	cd $(WEB_DIR) && npm install
	test -d $(VENV) || python3 -m venv $(VENV)
	cd $(API_DIR) && $(VENV)/bin/pip install -e ".[dev]"

ONEDM_COMMIT := dde2205a70a2c70d1786503d198a795358c80ee4

install-ml:
	test -d vendor/One-DM || git clone https://github.com/dailenson/One-DM vendor/One-DM
	cd vendor/One-DM && git checkout $(ONEDM_COMMIT)
	cd $(API_DIR) && $(VENV)/bin/pip install -e ".[dev,ml]"

dev:
	@trap 'kill 0' INT TERM EXIT; \
	(cd $(API_DIR) && $(VENV)/bin/uvicorn hwai.main:app --app-dir src --reload --port 8000) & \
	(cd $(WEB_DIR) && npm run dev) & \
	wait

build:
	cd $(WEB_DIR) && npm run build
	cd $(API_DIR) && $(PY) -c "import hwai.main"

typecheck:
	cd $(WEB_DIR) && npm run typecheck
	cd $(API_DIR) && $(VENV)/bin/mypy src

lint:
	cd $(WEB_DIR) && npm run lint
	cd $(API_DIR) && $(VENV)/bin/ruff check . && $(VENV)/bin/ruff format --check .

test:
	cd $(API_DIR) && $(VENV)/bin/pytest
	cd $(WEB_DIR) && npm test

e2e:
	./scripts/e2e.sh

migrate:
	cd $(API_DIR) && $(VENV)/bin/alembic upgrade head
