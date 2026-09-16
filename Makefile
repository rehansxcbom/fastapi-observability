SHELL := /bin/bash

.PHONY: help up down restart reset logs test lint format check change-password

help:
	@echo "Available commands:"
	@echo "  make up              - Start the Docker stack interactively (prompts for DB password)"
	@echo "  make down            - Stop and remove the Docker containers"
	@echo "  make restart         - Rebuild and restart the Docker stack"
	@echo "  make reset           - Wipe all containers and database volumes"
	@echo "  make logs            - Tail the logs of all Docker containers"
	@echo "  make test            - Run pytest suite"
	@echo "  make lint            - Run ruff to check code style and apply fixes"
	@echo "  make format          - Run ruff to format Python files"
	@echo "  make check           - Run format checking, linting, and tests (simulates CI)"
	@echo "  make change-password - Securely rotate the TimescaleDB admin password"

.PHONY: up
up:
	@PASS="$(DB_PASS)"; \
	while [ -z "$$PASS" ]; do \
		if ! read -s -p "🔑 Enter Database Password to start stack: " PASS; then \
			echo -e "\n❌ Input cancelled!"; exit 1; \
		fi; \
		echo ""; \
		if [ -z "$$PASS" ]; then \
			echo "❌ Error: Password cannot be empty. Please try again."; \
		fi; \
	done; \
	DB_PASSWORD=$$PASS DB_USER=admin DB_NAME=timeseries docker-compose up -d --build; \
	echo "✅ Stack launched successfully!"

.PHONY: down
down:
	docker-compose down

.PHONY: restart
restart:
	docker-compose down
	docker-compose up -d --build

.PHONY: reset
reset:
	@echo "⚠️  Wiping all containers and database volumes..."
	docker-compose down -v --remove-orphans
	docker volume prune -f
	@echo "✅ Reset complete! Run 'make up' to start fresh."

.PHONY: logs
logs:
	docker-compose logs -f

.PHONY: test
test:
	pytest

.PHONY: lint
lint:
	ruff check --fix .

.PHONY: format
format:
	ruff format .

.PHONY: check
check:
	ruff check .
	ruff format --check .
	pytest

.PHONY: change-password
change-password:
	@PASS="$(NEW_PASS)"; \
	echo "⚠️  This will change the password for the 'admin' database user."; \
	while [ -z "$$PASS" ]; do \
		if ! read -s -p "🔑 Enter NEW Database Password: " PASS; then \
			echo -e "\n❌ Input cancelled!"; exit 1; \
		fi; \
		echo ""; \
		if [ -z "$$PASS" ]; then \
			echo "❌ Error: Password cannot be empty. Please try again."; \
			continue; \
		fi; \
		if ! read -s -p "🔁 Confirm NEW Database Password: " PASS_CONFIRM; then \
			echo -e "\n❌ Input cancelled!"; exit 1; \
		fi; \
		echo ""; \
		if [ "$$PASS" != "$$PASS_CONFIRM" ]; then \
			echo "❌ Error: Passwords do not match! Please try again."; \
			PASS=""; \
		fi; \
	done; \
	echo "🔄 Updating password in TimescaleDB..."; \
	docker-compose exec -T timescaledb psql -U admin -d timeseries -c "ALTER USER admin WITH PASSWORD '$$PASS';" ; \
	echo "🔄 Restarting FastAPI to use the new credentials..."; \
	DB_PASSWORD=$$PASS DB_USER=admin DB_NAME=timeseries docker-compose up -d fastapi ; \
	echo "✅ Password changed successfully!"
