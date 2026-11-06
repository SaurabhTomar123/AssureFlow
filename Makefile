PY ?= python

.PHONY: up down migrate seed reset fixtures test lint typecheck health demo bootstrap acceptance

up:            ## start db, api and worker
	docker compose up -d --build db migrate api worker

down:
	docker compose down

migrate:
	$(PY) -m alembic upgrade head

seed reset:    ## idempotent; refuses outside demo/test
	$(PY) -m seed.loader

fixtures:      ## regenerate the 21 synthetic documents (deterministic)
	$(PY) -m seed.make_fixtures

test:          ## offline CI: fixtures, fake model, mocked Switch, real PostgreSQL
	$(PY) -m pytest tests/offline

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy

health:
	$(PY) -m scripts.health

demo:          ## the full correction-to-export demo against an in-memory Switch, printed as room transcripts
	$(PY) -m scripts.demo_offline

bootstrap:     ## after the manual chat setup: register the agent and bind rooms (see README)
	$(PY) -m scripts.admin register-agent
	$(PY) -m scripts.admin bind-rooms

acceptance:    ## offline acceptance run with a machine-generated report (docs/release/)
	$(PY) -m scripts.acceptance
