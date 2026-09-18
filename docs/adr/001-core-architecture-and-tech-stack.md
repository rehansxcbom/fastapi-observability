# ADR 001: Core Architecture for Secure, Observable Time-Series API

**Date:** September 2026

**Status:** Accepted

## 1. Context and Problem Statement

We require a foundational boilerplate for a time-series ingestion API. The system must support high-throughput asynchronous database operations, provide granular full-stack observability without vendor lock-in, and enforce strict "Defense-in-Depth" security principles from the container level up to the application layer. Developer experience (DX) and local testing must remain fast and reliable.

## 2. Architecture Decisions

### 2.1 Application and Database Layer

* **Decision:** FastAPI + SQLModel utilizing the asynchronous `asyncpg` driver.
* **Rationale:** Time-series ingestion is highly I/O bound. The async driver prevents thread exhaustion under heavy load, allowing the event loop to process thousands of requests concurrently.
* **Decision:** TimescaleDB with Composite Primary Keys.
* **Rationale:** TimescaleDB provides native PostgreSQL partitioning for time-series data. We use a composite primary key (`time` + `server_id`) to prevent unique constraint violations during highly concurrent metric submissions. Data boundaries are enforced at the API boundary via Pydantic to prevent invalid data processing.

### 2.2 Observability Stack

* **Decision:** OpenTelemetry (OTel) + Grafana LGTM Stack (Loki, Grafana, Tempo, Prometheus).
* **Rationale:** We mandate vendor-agnostic telemetry. The application uses OTel auto-instrumentation to generate traces and metrics without polluting business logic. All telemetry is routed through a central **OpenTelemetry Collector**, allowing us to swap backend providers in the future without modifying the application code. Persistent Docker volumes guarantee observability state survives local container restarts.

### 2.3 Container and Infrastructure Security

* **Decision:** Unprivileged Multi-Stage Docker Builds.
* **Rationale:** We utilize isolated Python virtual environments (`/opt/venv`) built in a compilation stage to keep the production image tiny and free of build tools.* **Decision:** Diskless Secrets Management.
* **Rationale:** To prevent credential leakage, we forbid `.env` files for database passwords. Credentials are injected directly into the ephemeral Docker environment via interactive terminal prompts orchestrated by a `Makefile`.
* **Decision:** Host Defense Mechanisms.
* **Rationale:** Containers run with dropped Linux capabilities (`cap_drop: ALL`) to prevent container escapes, and memory limits are enforced to prevent application memory leaks from triggering host OS kernel panics.

### 2.4 Testing and Quality Assurance

* **Decision:** FastAPI Dependency Injection for Database Sessions.
* **Rationale:** Standard Python mocking (`unittest.mock.patch`) relies on fragile string paths that break during file refactoring. FastAPI's `dependency_overrides` allows us to securely swap the database session for an `AsyncMock` object, enabling instantaneous, offline CI testing.
* **Decision:** Bandit for Static Application Security Testing (SAST).
* **Rationale:** The CI pipeline enforces Bandit scanning to proactively block raw SQL injection vulnerabilities and hardcoded secrets from being merged into the main branch.

## 3. Consequences

### Positive

* **Security Posture:** The application is highly resilient to SQL injection, credential leaks, and container breakout attacks.
* **Performance:** Bulk asynchronous inserts can handle massive scale without blocking the API.
* **Maintainability:** Unlocked dependencies allow for rapid feature co-development, while the CI pipeline catches regressions automatically.

### Negative / Trade-offs

* **Onboarding Friction:** Developers cannot simply run `docker-compose up`. They must use the `Makefile` and interactively supply passwords, requiring documentation reading.
* **Testing Complexity:** Developers must understand async Python paradigms and FastAPI's dependency injection system to write effective unit tests.

---

