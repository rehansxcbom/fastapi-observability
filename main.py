import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import Field, SQLModel, text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Diskless secrets injected via environment
USER = os.getenv("DB_USER", "admin")
PASSWORD = os.getenv("DB_PASSWORD", "secretpassword")
DB_NAME = os.getenv("DB_NAME", "timeseries")
HOST = os.getenv("DB_HOST", "timescaledb")

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


# 3. Database Model: Used exclusively by SQLAlchemy to interact with the database
class ServerMetric(ServerMetricBase, table=True):
    __tablename__ = "server_metrics"
    # The database auto-generates the timestamp when the record is created
    time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), primary_key=True
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


@app.post("/metrics/", status_code=201)
async def record_metrics(
    metrics: list[
        ServerMetricCreate
    ],  # <-- FastAPI strictly validates using the Create model
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Accepts a list of metrics for highly efficient bulk database insertion."""

    # Convert validated Pydantic API models into SQLAlchemy Database models
    db_metrics = [ServerMetric.model_validate(metric) for metric in metrics]

    session.add_all(db_metrics)
    await session.commit()
    return {"status": f"{len(metrics)} metrics recorded successfully"}


# Instrument FastAPI application
FastAPIInstrumentor.instrument_app(app)
