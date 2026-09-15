# FastAPI Observability Stack

[![CI Pipeline](https://github.com/rehansxcbom/fastapi-observability/actions/workflows/ci.yml/badge.svg)](https://github.com/rehansxcbom/fastapi-observability/actions/workflows/ci.yml)

This repository provides a containerized FastAPI application fully instrumented with OpenTelemetry to automatically generate and export telemetry data. It includes a pre-configured Docker orchestration setup to route this data into a modern observability backend.

## System Architecture

The stack implements the core pillars of observability:
* **FastAPI:** The primary Python application, utilizing zero-code instrumentation via the OpenTelemetry SDK to track requests without manual code changes.
* **Tempo:** A distributed tracing system that receives and stores the generated trace spans via the OTLP gRPC protocol.
* **Prometheus:** An open-source monitoring toolkit configured to scrape and store time-series metrics from the FastAPI service.
* **Loki & Promtail:** Promtail acts as a local agent that automatically discovers and scrapes Docker container logs (such as Uvicorn output) and pushes them to Loki, a highly scalable log aggregation system.
* **Grafana:** A unified visualization platform to query traces in Tempo, explore container logs in Loki, and build metric dashboards from Prometheus.

## Prerequisites

Ensure Docker and Docker Compose are installed on your local machine.

## Getting Started

1. **Launch the Stack:** Build the image and start the containers.
   ```bash
   docker-compose up -d --build
   ```
2. **Generate Traffic:** Open a browser and visit `http://127.0.0.1:8000` to trigger HTTP requests and generate OpenTelemetry data.
3. **View Metrics (Prometheus):** Access the raw metric targets at `http://127.0.0.1:9090` to confirm time-series data is being successfully scraped.
4. **Visualize Data (Grafana):** Navigate to `http://127.0.0.1:3000` to build dashboards, query your application's trace logs, and search through your collected Loki logs.

## Extending the Application (Adding Endpoints)

Because this project uses the `FastAPIInstrumentor`, any new routes you add to the application are automatically instrumented. You do not need to write custom trace or metric code for basic HTTP monitoring.

To add a new endpoint, simply open `main.py` and define your new route above the `FastAPIInstrumentor.instrument_app(app)` line:

```python
@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id, "status": "Found"}
```
