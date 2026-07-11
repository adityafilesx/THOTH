.PHONY: setup daemon desktop dev test test-daemon test-desktop lint typecheck build migrate schemas clean

DAEMON := apps/daemon
DESKTOP := apps/desktop

setup: ## Install all dependencies
	uv sync --project $(DAEMON)
	pnpm install

daemon: ## Run the FastAPI daemon (http://127.0.0.1:7710)
	uv run --project $(DAEMON) python -m thoth_daemon.main

desktop: ## Run the desktop dev server (browser mode)
	pnpm -C $(DESKTOP) dev

dev: ## Run daemon and desktop together
	$(MAKE) -j2 daemon desktop

migrate: ## Apply database migrations
	cd $(DAEMON) && uv run alembic upgrade head

test: test-daemon test-desktop ## Run all tests

test-daemon:
	uv run --project $(DAEMON) pytest $(DAEMON)/tests

test-desktop:
	pnpm -C $(DESKTOP) test

lint: ## Lint daemon and desktop
	uv run --project $(DAEMON) ruff check $(DAEMON)
	uv run --project $(DAEMON) ruff format --check $(DAEMON)
	pnpm -C $(DESKTOP) lint

typecheck: ## Type-check daemon and desktop
	uv run --project $(DAEMON) mypy $(DAEMON)/src
	pnpm -C $(DESKTOP) typecheck

build: ## Production build of the frontend
	pnpm -C $(DESKTOP) build

schemas: ## Regenerate packages/shared-schemas from Pydantic contracts
	uv run --project $(DAEMON) python -m thoth_daemon.schemas.export ../../packages/shared-schemas/schemas

clean:
	rm -rf $(DESKTOP)/dist $(DAEMON)/.pytest_cache .ruff_cache .mypy_cache
