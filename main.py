import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Body, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import Column, DateTime
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import Field, SQLModel, text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_secret(secret_name: str, env_var: str) -> str:
    """
    Securely fetches a secret, preferring memory-mounted Docker secrets over env vars.
    CRASHES the application if the secret is missing.
    """
    # 1. Try to read from Docker Secrets (Diskless / memory-mapped file)
    secret_path = f"/run/secrets/{secret_name}"
    if os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            return f.read().strip()

    # 2. Fall back to Environment Variable (No default guessable value!)
    val = os.getenv(env_var)
    if val:
        return val

    # 3. Fail Fast: Do not boot with a guessable password
    raise RuntimeError(
        f"CRITICAL SECURITY ERROR: Missing credential! "
        f"Could not find secret '{secret_name}' or env var '{env_var}'."
    )


# Diskless secrets injected via Docker Secrets or strict environment variables
USER = os.getenv("DB_USER", "admin")  # Usernames are generally safe to default
HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "timeseries")

# FIX: Password strictly requires a secure source
PASSWORD = get_secret("db_password", "DB_PASSWORD")

# Async connection string
DATABASE_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:5432/{DB_NAME}"
# Connection pool optimized for throughput and resilience
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

# Instrument the sync engine under the hood for traces
SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

# ==========================================
# ENTERPRISE MODEL SEPARATION
# ==========================================


# 1. Base Model: Holds fields common to all layers
class ServerMetricBase(SQLModel):
    server_id: str = Field(primary_key=True)
    cpu_utilization: float = Field(
        ge=0.0, le=100.0, description="Must be between 0 and 100"
    )


# 2. Create Model: Used exclusively by FastAPI for strict incoming validation
class ServerMetricCreate(ServerMetricBase):
    pass


class ServerMetric(ServerMetricBase, table=True):
    __tablename__ = "server_metrics"

    # We explicitly tell SQLAlchemy to use 'TIMESTAMP WITH TIME ZONE'
    time: datetime = Field(
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
            await session.commit()
        logger.info("Database initialized successfully.")
    except OperationalError as e:
        logger.error(f"Critical Database Startup Error: {e}")
        raise
    yield


app = FastAPI(lifespan=lifespan, title="Secure Observability API")

# ==========================================
# OPENTELEMETRY TRACER CONFIGURATION
# ==========================================

# 1. Identity: Tell the LGTM stack exactly what service is generating these traces
resource = Resource(attributes={SERVICE_NAME: "fastapi-telemetry-engine"})

# 2. Provider: Create the engine that generates spans
trace_provider = TracerProvider(resource=resource)

# 3. Exporter: Configure where the spans go (Defaulting to the OTel Collector gRPC port)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

# 4. Processor: Batch spans together for network efficiency rather than sending one-by-one
trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# 5. Global Registration: Lock this in as the default tracer for the whole application
trace.set_tracer_provider(trace_provider)

# Security: CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Security: Mask database errors from end users
@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )


# Dependency Injection for Database Sessions
async def get_session():
    async with AsyncSession(engine) as session:
        yield session


# API Endpoints
@app.get("/")
async def read_root():
    return {"message": "Hello, telemetry!"}


@app.get("/health")
async def health_check(session: Annotated[AsyncSession, Depends(get_session)]):
    """Robust readiness probe: verifies API is up AND Database is reachable."""
    try:
        # A lightweight query to verify the connection pool is healthy
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}

    # FIX: Catch specific database failures, not blind exceptions
    except SQLAlchemyError as e:
        logger.error(f"Healthcheck database failure: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "database": "disconnected"}
        )


@app.post("/metrics/", status_code=201)
async def record_metrics(
    # FIX: Enforce a strict limit of 1000 items per request
    metrics: Annotated[list[ServerMetricCreate], Body(max_length=1000)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Accepts a list of metrics (max 1000) for highly efficient bulk database insertion."""

    db_metrics = [ServerMetric.model_validate(metric) for metric in metrics]
    session.add_all(db_metrics)
    await session.commit()
    return {"status": f"{len(metrics)} metrics recorded successfully"}


# Instrument FastAPI application
FastAPIInstrumentor.instrument_app(app)
