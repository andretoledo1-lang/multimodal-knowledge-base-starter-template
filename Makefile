# Multimodal KB — dev orchestration.
#   backend : FastAPI via uv      → http://localhost:8000
#   frontend: Vite via pnpm       → http://localhost:5173  (proxies /api → :8000)
#
# First time:  make install   then   make dev

BACKEND_DIR     := backend
FRONTEND_FILTER := --filter frontend
UVICORN         := uv run uvicorn app.main:app

.DEFAULT_GOAL := help
.PHONY: help install install-backend install-frontend dev backend frontend \
        build prod typecheck docker-build docker-run clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install backend + frontend deps

install-backend: ## Sync Python deps (uv)
	cd $(BACKEND_DIR) && uv sync

install-frontend: ## Install JS deps (pnpm workspace)
	pnpm install

dev: ## Run backend + frontend together (Ctrl-C stops both)
	@echo "→ backend  http://localhost:8000"
	@echo "→ frontend http://localhost:5173"
	@trap 'kill 0' INT TERM EXIT; \
		( cd $(BACKEND_DIR) && $(UVICORN) --reload --port 8000 ) & \
		pnpm $(FRONTEND_FILTER) dev & \
		wait

backend: ## Run only the FastAPI backend (auto-reload)
	cd $(BACKEND_DIR) && $(UVICORN) --reload --port 8000

frontend: ## Run only the Vite dev server
	pnpm $(FRONTEND_FILTER) dev

build: ## Build the SPA into backend/static/
	pnpm $(FRONTEND_FILTER) build

prod: build ## Build the SPA, then serve API + UI on :8000
	cd $(BACKEND_DIR) && $(UVICORN) --port 8000

typecheck: ## Type-check the frontend
	pnpm $(FRONTEND_FILTER) typecheck

docker-build: ## Build the Docker image
	docker build -t multimodal-kb .

docker-run: ## Run the image (needs GEMINI_API_KEY in the environment)
	docker run --rm -e GEMINI_API_KEY="$$GEMINI_API_KEY" -p 8000:8000 \
		-v "$$(pwd)/data/chroma:/app/backend/chroma_db" \
		-v "$$(pwd)/data/uploads:/app/backend/uploads" \
		multimodal-kb

clean: ## Remove build output and installed deps
	rm -rf node_modules frontend/node_modules backend/static frontend/dist
