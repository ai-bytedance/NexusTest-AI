.PHONY: up down logs shell migrate revision downgrade lint format test ci

COMPOSE_FILE=infra/docker-compose.yml
COMPOSE_ENV=COMPOSE_DOCKER_CLI_BUILD=0 DOCKER_BUILDKIT=0
DOCKER_COMPOSE_CMD=$(COMPOSE_ENV) docker compose -f $(COMPOSE_FILE)
PYTHON ?= python3
PRE_COMMIT ?= pre-commit
PYTEST ?= pytest
BACKEND_DIR ?= backend
TEST_DIR ?= $(BACKEND_DIR)/tests

up:
    $(DOCKER_COMPOSE_CMD) up -d --build

down:
    $(DOCKER_COMPOSE_CMD) down

logs:
    $(DOCKER_COMPOSE_CMD) logs -f

shell:
    $(DOCKER_COMPOSE_CMD) exec api /bin/bash

migrate:
    $(DOCKER_COMPOSE_CMD) run --rm api alembic upgrade head

revision:
ifndef msg
    $(error msg is required. usage: make revision msg="message")
endif
    $(DOCKER_COMPOSE_CMD) run --rm api alembic revision --autogenerate -m "$(msg)"

downgrade:
    $(DOCKER_COMPOSE_CMD) run --rm api alembic downgrade -1

lint:
    $(PRE_COMMIT) run --all-files --show-diff-on-failure

format:
    $(PYTHON) -m black $(BACKEND_DIR)
    $(PYTHON) -m isort --profile black $(BACKEND_DIR)

test:
    $(PYTHON) -m $(PYTEST) $(TEST_DIR)

ci: lint test
