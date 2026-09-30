
# FastAPI Observability Stack

[![CI Pipeline](https://github.com/rehansxcbom/fastapi-observability/actions/workflows/ci.yml/badge.svg)](https://github.com/rehansxcbom/fastapi-observability/actions/workflows/ci.yml)

This repository provides a containerized FastAPI application fully instrumented with OpenTelemetry to automatically generate and export telemetry data. It includes a pre-configured Docker orchestration setup to route this data into a modern observability backend.


## System Architecture

The stack implements the core pillars of observability:
* Continuous Integration: This project uses a **continuous integration workflow** using GitHub Actions. This automated pipeline triggers whenever code is pushed to or pulled into the **main branch**. To maintain security best practices, the workflow strictly limits the **GITHUB\_TOKEN permissions** to reading repository contents. The execution environment runs on an **Ubuntu runner** and is specifically configured to utilize Python version 3.11 alongside pip caching. Throughout the process, the pipeline retrieves the code repository, installs necessary project dependencies, and verifies code standards utilizing **Ruff**. Finally, the system executes a **Bandit security scan** and runs a **pytest** test suite.
* **FastAPI & SQLModel:** Asynchronous web framework leveraging `asyncpg` for high-throughput non-blocking database queries and Pydantic for strict input validation.
* **Tempo:** A distributed tracing system that receives and stores the generated trace spans via the OTLP gRPC protocol.
* **Prometheus:** An open-source monitoring toolkit configured to scrape and store time-series metrics from the FastAPI service.
* **Loki & Alloy:** Alloy acts as a local agent that automatically discovers and scrapes Docker container logs (such as Uvicorn output) and pushes them to Loki, a highly scalable log aggregation system.
* **TimescaleDB:** A PostgreSQL extension optimized for time-series metrics, configured with composite primary keys (`time` + `server_id`) to prevent insertion collisions.
* **OpenTelemetry:** Zero-code auto-instrumentation for tracing and metrics, routed centrally via the **OpenTelemetry Collector**.
* **Grafana:** A unified visualization platform to query traces in Tempo, explore container logs in Loki, and build metric dashboards from Prometheus.
* **Container Security:** Multi-stage builds utilizing isolated Python virtual environments (`/opt/venv`) and healthchecks.


## Prerequisites

Ensure Docker and Docker Compose are installed on your local machine.


## System Flow


```mermaid
flowchart LR
    Client([External Client])

    subgraph Application["Production Workload"]
        direction TB
        API["FastAPI\n(Async Web Server)"]
        TSDB[("TimescaleDB\n(Time-Series Data)")]
    end

    subgraph Telemetry["Data Collection"]
        direction TB
        OTel{{"OpenTelemetry\n(Traces & Metrics)"}}
        Alloy{{"Alloy\n(Log Scraper)"}}
    end

    subgraph LGTM["Observability Backends"]
        direction TB
        Tempo[("Tempo\n(Traces)")]
        Prom[("Prometheus\n(Metrics)")]
        Loki[("Loki\n(Logs)")]
    end

    Grafana["Grafana\n(Unified UI)"]

    %% Core Business Flow (Animated)
    Client e1@-->|"HTTP POST\n/metrics/"| API
    e1@{ animate: true }
    
    API e2@==>|"asyncpg\nParameterized INSERT"| TSDB
    e2@{ animate: true, animation: slow }

    %% Telemetry Routing (Animated)
    API e3@-.->|"OTLP (gRPC)"| OTel
    e3@{ animate: true }
    
    API e4@-.->|"stdout / stderr"| Alloy
    e4@{ animate: true }

    OTel e5@-.->|"OTLP Exporter"| Tempo
    e5@{ animate: true }
    
    OTel e6@-.->|"Prometheus Exporter"| Prom
    e6@{ animate: true }
    
    Alloy e7@-.->|"Push API"| Loki
    e7@{ animate: true }

    %% Dashboard Visualization (Static - represents queries, not streams)
    Tempo -. "TraceQL" .-> Grafana
    Prom -. "PromQL" .-> Grafana
    Loki -. "LogQL" .-> Grafana
    TSDB -. "SQL" .-> Grafana
```



## Services & Ports

| Service | Port | Description |
|---|---|---|
| **FastAPI** | `8000` | Asynchronous core Python web API. |
| **Grafana** | `3000` | Unified UI for dashboards, metrics, and traces. |
| **Prometheus** | `9090` | Time-series database UI for performance counters. |
| **Tempo** | `3200` | Distributed tracing backend UI. |
| **OTel Collector** | `4317` | Central OTLP telemetry receiver (gRPC). |
| **Loki** | `3100` | Log aggregation database. |
| **TimescaleDB** | `5432` | PostgreSQL time-series storage backend. |


## Security & Secrets Management

This project enforces a **diskless secrets management** policy. Database credentials are never stored in static `.env` files or committed to source control. Instead, they are dynamically injected into the Docker environment directly from your terminal session via the `Makefile`. All endpoints interacting with the database utilize parameterized ORM queries to eliminate SQL injection vulnerabilities.


## Getting Started

1. **Describe your TimescaleDB config:**
  Set up your TimescaleDB system which is omitted in etc/grafana/provisioning/datasources.yaml to avoid a static password for the database.

  ```yaml
  apiVersion: 1

  datasources:
    - name: TimescaleDB
      type: postgres
      access: proxy
      url: localhost:5432
      database: timeseries
      user: admin
      secureJsonData:
        password: your_database_password
      jsonData:
        sslmode: disable # Options: disable, require, verify-ca, verify-full
        postgresVersion: 1500 # Set according to your PostgreSQL version (e.g., 1400, 1500, 1600)
        timescaledb: true # Enables TimescaleDB-specific optimizations in Grafana
      editable: true
```


2. **Launch the Stack:**
   Run the interactive Makefile command. It will prompt you to securely supply a database password while validating input to ensure it is not empty.

  ```bash
   make up
  ```

3. **Speed Test Server:**
  Use K6 to create 50 virtual users and 1m20s max duration (up to 50 looping VUs for 50s over 3 stages gracefulRampDown: 30s, gracefulStop: 30s)

  ```bash
   make load-test
  ```

4. **Load Test Server:**
  Use locust to create 10 virtual users and 5m max duration (up to 10 looping VUs for 5m making upto 70 requests) 

  ```bash
   make speed-test
   ```

5. **Explore Observability:** :
   Open `http://127.0.0.1:3000` (Grafana) to explore your persistent dashboards, query application logs via Loki, and inspect query latency via Tempo traces.


## Operational Makefile Commands

Run `make help` to view all available commands. Key workflows include:

*   **Factory Reset (Wipe Volumes & Containers):** `make reset`
*   **Run Local Checks (Linting, Formatting, & Testing):** `make check`
*   **Watch Live Logs:** `make logs`


## Testing & Dependency Injection

The test suite uses FastAPI's native **Dependency Injection** (`app.dependency_overrides`) combined with `unittest.mock.AsyncMock`. This allows the test suite to execute locally in milliseconds without requiring an active TimescaleDB container instance, enabling true offline testing. Code formatting and linting are strictly enforced via Ruff.
