.PHONY: up down logs seed ingest sources test lint dev-api dev-web

up:            ## build and start db + api + web
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api web

seed:          ## taxonomy + demo events + register the real API sources (inside the api container)
	docker compose exec api python -m app.cli seed

ingest:        ## fetch real events from every enabled source (World Triathlon, RunSignup, Wikidata, ...)
	docker compose exec api python -m app.cli run-all

sources:       ## which real data sources are ready / need credentials
	docker compose exec api python -m app.cli catalog

test:          ## backend tests (needs a local Postgres; see README)
	cd backend && .venv/bin/pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests && cd ../frontend && npx tsc --noEmit && npx eslint .

dev-api:       ## run the API locally with auto-reload
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && npm run dev
