.PHONY: dev test lint migrate seed security-check build clean help

BACKEND_DIR=backend
MOBILE_DIR=mobile

# ==============================================================================
# Development
# ==============================================================================

dev:  ## Start all services (Docker Compose)
	docker compose up --build

dev-backend:  ## Start backend only (no Docker)
	cd $(BACKEND_DIR) && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

down:  ## Stop all services
	docker compose down

# ==============================================================================
# Database
# ==============================================================================

migrate:  ## Run Alembic database migrations
	docker compose exec backend alembic upgrade head

migrate-local:  ## Run migrations locally (non-Docker)
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-down:  ## Rollback last migration
	docker compose exec backend alembic downgrade -1

seed:  ## Seed development data
	docker compose exec backend python -m app.db.seed

# ==============================================================================
# Testing
# ==============================================================================

test:  ## Run all backend tests
	cd $(BACKEND_DIR) && pytest -v --tb=short

test-cov:  ## Run tests with coverage
	cd $(BACKEND_DIR) && pytest -v --cov=app --cov-report=html --cov-report=term-missing

test-security:  ## Run security-focused tests only
	cd $(BACKEND_DIR) && pytest -v -m security

# ==============================================================================
# Code Quality
# ==============================================================================

lint:  ## Run ruff linter
	cd $(BACKEND_DIR) && ruff check app tests

lint-fix:  ## Auto-fix ruff issues
	cd $(BACKEND_DIR) && ruff check --fix app tests

format:  ## Format code with ruff formatter
	cd $(BACKEND_DIR) && ruff format app tests

typecheck:  ## Run mypy type checker
	cd $(BACKEND_DIR) && mypy app

# ==============================================================================
# Security
# ==============================================================================

security-check:  ## Run all security tools
	@echo "=== Ruff lint ==="
	cd $(BACKEND_DIR) && ruff check app tests
	@echo "=== Mypy type check ==="
	cd $(BACKEND_DIR) && mypy app
	@echo "=== Bandit SAST ==="
	cd $(BACKEND_DIR) && bandit -r app -ll
	@echo "=== pip-audit dependency scan ==="
	cd $(BACKEND_DIR) && pip-audit
	@echo "=== Security check complete ==="

pip-audit:  ## Audit Python dependencies for known vulnerabilities
	cd $(BACKEND_DIR) && pip-audit

bandit:  ## Run Bandit SAST scanner
	cd $(BACKEND_DIR) && bandit -r app -ll -f json -o bandit-report.json || true
	cat $(BACKEND_DIR)/bandit-report.json

# ==============================================================================
# Mobile
# ==============================================================================

mobile-install:  ## Install mobile dependencies
	cd $(MOBILE_DIR) && npm install

mobile-start:  ## Start Expo dev server
	cd $(MOBILE_DIR) && npx expo start

mobile-android:  ## Run on Android emulator
	cd $(MOBILE_DIR) && npx expo start --android

mobile-ios:  ## Run on iOS simulator
	cd $(MOBILE_DIR) && npx expo start --ios

mobile-lint:  ## Lint mobile TypeScript
	cd $(MOBILE_DIR) && npm run lint

mobile-typecheck:  ## Type-check mobile TypeScript
	cd $(MOBILE_DIR) && npm run typecheck

# ==============================================================================
# Build
# ==============================================================================

build-backend:  ## Build backend Docker image
	docker build -t mindai-backend:latest $(BACKEND_DIR)

build-all:  ## Build all Docker images
	docker compose build

# ==============================================================================
# Cleanup
# ==============================================================================

clean:  ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	cd $(BACKEND_DIR) && rm -f bandit-report.json

clean-data:  ## Remove local dev data volumes (DESTRUCTIVE)
	docker compose down -v
	rm -rf data/uploads/*

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
