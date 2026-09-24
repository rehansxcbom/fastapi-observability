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
	@echo "  make speed-test      - Run a k6 load test to generate traffic"
	@echo "  make load-test       - Run a locust load test to generate traffic"

# Suppress command echoing so the password isn't printed to the terminal history
.PHONY: up
up:
	@echo "🚀 Securely booting observability stack..."
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
	DB_PASSWORD=$$PASS DB_USER=admin DB_NAME=timeseries docker compose up -d --build; \
	echo "✅ Stack launched successfully!"

.PHONY: down
down:
	docker compose down

.PHONY: restart
restart:
	docker compose down
	docker compose up -d --build

.PHONY: reset
reset:
	@echo "⚠️  Wiping all containers and database volumes..."
	docker compose down -v --remove-orphans
	docker volume prune -f
	@echo "✅ Reset complete! Run 'make up' to start fresh."

.PHONY: logs
logs:
	docker compose logs -f

.PHONY: test
test:
	OTEL_SDK_DISABLED=true DB_PASSWORD=mock_test_password DB_USER=postgres DB_NAME=telemetry pytest

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
	OTEL_SDK_DISABLED=true DB_PASSWORD=mock_test_password DB_USER=postgres DB_NAME=telemetry pytest


.PHONY: speed-test
speed-test:
	@echo "🔥 Generating traffic to spike CPU and Memory..."
	docker run --rm -i --add-host host.docker.internal:host-gateway grafana/k6 run - < speed-test.js

.PHONY: load-test
load-test:
	@echo "🔥 Generating traffic to spike CPU and Memory..."
	locust -f load-test.py --headless --users 10 --spawn-rate 1 -H http://localhost:8000 --run-time 5m


