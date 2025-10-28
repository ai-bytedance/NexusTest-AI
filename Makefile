.PHONY: up down logs shell migrate revision downgrade

COMPOSE_FILE=infra/docker-compose.yml

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
