import asyncio
import logging
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import httpx2
import names
from fastapi import Body, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import Column, DateTime
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import Field, SQLModel, text
from starlette.background import BackgroundTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_ONE_HOST = os.environ.get("TARGET_ONE_HOST", "app-b")
TARGET_TWO_HOST = os.environ.get("TARGET_TWO_HOST", "app-c")


def get_secret(secret_name: str, env_var: str) -> str:
    secret_path = f"/run/secrets/{secret_name}"
    if os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            return f.read().strip()
    val = os.getenv(env_var)
    if val:
        return val
    raise RuntimeError(
        f"CRITICAL SECURITY ERROR: Missing credential! "
        f"Could not find secret '{secret_name}' or env var '{env_var}'."
    )


# --- Database Configuration ---
USER = os.getenv("DB_USER", "admin")
HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "timeseries")
PASSWORD = get_secret("db_password", "DB_PASSWORD")

DATABASE_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:5432/{DB_NAME}"
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)


# --- Models ---
class ServerMetricBase(SQLModel):
    user_id: str = Field(index=True)
    user_token: float = Field(ge=0.0, le=100.0, description="Must be between 0 and 100")
    # Expose time so clients can send historical/buffered timestamps
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServerMetricCreate(ServerMetricBase):
    pass


class ServerMetric(ServerMetricBase, table=True):
    __tablename__ = "server_metrics"
    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), primary_key=True),
    )


class RequestMetricBase(SQLModel):
    user_id: str = Field(index=True, description="ID of the user making the request")
    username: str | None = Field(default=None, description="Username, if available")
    request_code: int = Field(description="HTTP Status Code (e.g., 200, 404, 500)")
    request_duration_ms: float = Field(
        ge=0.0, description="Duration of the request in milliseconds"
    )
    method: str = Field(description="HTTP method (GET, POST, etc.)")
    path: str = Field(description="The URL path of the request")
    ip_address: str | None = Field(default=None)


class RequestMetricCreate(RequestMetricBase):
    pass


class RequestMetric(RequestMetricBase, table=True):
    __tablename__ = "request_metrics"
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    request_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), primary_key=True),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as session:
            await session.execute(
                text(
                    "SELECT create_hypertable('server_metrics', 'time', if_not_exists => TRUE);"
                )
            )
            await session.execute(
                text(
                    "SELECT create_hypertable('request_metrics', 'request_time', if_not_exists => TRUE);"
                )
            )
            await session.commit()
        logger.info("Database initialized and hypertables created successfully.")
    except OperationalError as e:
        logger.error(f"Critical Database Startup Error: {e}")
        raise
    yield


app = FastAPI(lifespan=lifespan, title="Secure Observability API")

resource = Resource(attributes={SERVICE_NAME: "fastapi-telemetry-engine"})
trace_provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(trace_provider)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )


async def get_session():
    async with AsyncSession(engine) as session:
        yield session


async def save_request_metric_task(metric: RequestMetric):
    try:
        async with AsyncSession(engine) as session:
            session.add(metric)
            await session.commit()
    except SQLAlchemyError as e:
        logger.error(f"Failed to record request metric in background: {e}")


@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    request_start_datetime = datetime.now(timezone.utc)
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time_ms = (time.perf_counter() - start_time) * 1000

    user_id = request.headers.get("X-User-Id", str(uuid.uuid4()))
    username = request.headers.get("X-Username", names.get_full_name())

    metric = RequestMetric(
        request_time=request_start_datetime,
        user_id=user_id,
        username=username,
        request_code=response.status_code,
        request_duration_ms=process_time_ms,
        method=request.method,
        path=request.url.path,
        ip_address=request.client.host if request.client else "unknown",
    )

    response.background = BackgroundTask(save_request_metric_task, metric)

    return response


@app.get("/")
async def read_root():
    return {"message": "Hello, telemetry!"}


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str | None = None):
    logger.error("items")
    return {"item_id": item_id, "q": q}


@app.get("/error_test")
async def error_test(response: Response):
    logger.error("got error!!!!")
    raise ValueError("value error")


@app.get("/chain")
async def chain(response: Response):
    headers = {}
    inject(headers)  # inject trace info to header
    logger.critical(headers)

    try:
        async with httpx2.AsyncClient() as client:
            await client.get(
                "http://localhost:8000/",
                headers=headers,
            )
        async with httpx2.AsyncClient() as client:
            await client.get(
                f"http://{TARGET_ONE_HOST}:8000/io_task",
                headers=headers,
            )
        async with httpx2.AsyncClient() as client:
            await client.get(
                f"http://{TARGET_TWO_HOST}:8000/cpu_task",
                headers=headers,
            )
    except httpx2.RequestError as e:
        logger.error(f"An HTTP error occurred during the chain request: {e}")

    logger.info("Chain Finished")
    return {"path": "/chain"}


@app.get("/io_task")
async def io_task():
    await asyncio.sleep(1)
    logger.error("io task")
    return "IO bound task finish!"


@app.get("/cpu_task")
async def cpu_task():
    for i in range(1000):
        _ = i * i * i
    logger.error("cpu task")
    return "CPU bound task finish!"


@app.get("/random_status")
async def random_status(response: Response):
    response.status_code = random.choice([200, 200, 300, 400, 500])
    logger.error("random status")
    return {"path": "/random_status"}


@app.get("/random_sleep")
async def random_sleep(response: Response):
    await asyncio.sleep(random.randint(0, 5))
    logger.error("random sleep")
    return {"path": "/random_sleep"}


@app.get("/health")
async def health_check(session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except SQLAlchemyError as e:
        logger.error(f"Healthcheck database failure: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "database": "disconnected"}
        )


@app.post("/server-metrics/", status_code=201)
async def record_server_metrics(
    metrics: Annotated[list[ServerMetricCreate], Body(max_length=1000)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    db_metrics = [ServerMetric.model_validate(metric) for metric in metrics]
    session.add_all(db_metrics)
    await session.commit()
    return {"status": f"{len(metrics)} server metrics recorded successfully"}


@app.post("/request-metrics/", status_code=201)
async def record_request_metrics(
    metrics: Annotated[list[RequestMetricCreate], Body(max_length=1000)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    db_metrics = [RequestMetric.model_validate(metric) for metric in metrics]
    session.add_all(db_metrics)
    await session.commit()
    return {"status": f"{len(metrics)} request metrics recorded successfully"}


FastAPIInstrumentor.instrument_app(app)
