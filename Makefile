.PHONY: up down logs shell migrate revision downgrade lint format test ci

COMPOSE_FILE=infra/docker-compose.yml
PYTHON ?= python3
PRE_COMMIT ?= pre-commit
PYTEST ?= pytest
BACKEND_DIR ?= backend
TEST_DIR ?= $(BACKEND_DIR)/tests

up:
    docker compose -f $(COMPOSE_FILE) up -d --build

down:
    docker compose -f $(COMPOSE_FILE) down

logs:
    docker compose -f $(COMPOSE_FILE) logs -f

shell:
    docker compose -f $(COMPOSE_FILE) exec api /bin/bash

migrate:
    docker compose -f $(COMPOSE_FILE) run --rm api alembic upgrade head

revision:
ifndef msg
    $(error msg is required. usage: make revision msg="message")
endif
    docker compose -f $(COMPOSE_FILE) run --rm api alembic revision --autogenerate -m "$(msg)"

downgrade:
    docker compose -f $(COMPOSE_FILE) run --rm api alembic downgrade -1

lint:
    $(PRE_COMMIT) run --all-files --show-diff-on-failure

format:
    $(PYTHON) -m black $(BACKEND_DIR)
    $(PYTHON) -m isort --profile black $(BACKEND_DIR)

test:
    $(PYTHON) -m $(PYTEST) $(TEST_DIR)

ci: lint test
