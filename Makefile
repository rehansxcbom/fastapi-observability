# Force make to use bash for interactive prompts
SHELL := /bin/bash

.PHONY: help up down restart logs test lint format check

help:
	@echo "Available commands:"
	@echo "  make up      - Start the Docker stack in the background"
	@echo "  make down    - Stop and remove the Docker containers"
	@echo "  make restart - Rebuild and restart the Docker stack"
	@echo "  make logs    - Tail the logs of all Docker containers"
	@echo "  make test    - Run pytest suite"
	@echo "  make lint    - Run ruff to check code style and apply fixes"
	@echo "  make format  - Run ruff to format Python files"
	@echo "  make check   - Run format checking, linting, and tests (simulates CI)"

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

down:
	docker-compose down

restart:
	docker-compose down
	docker-compose up -d --build

reset:
	@echo "⚠️  Wiping all containers and database volumes..."
	docker-compose down -v --remove-orphans
	@echo "✅ Reset complete! Run 'make up' to start fresh."

logs:
	docker-compose logs -f

test:
	pytest

lint:
	ruff check --fix .

format:
	ruff format .

check:
	ruff format --check .
	ruff check .
	pytest

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
