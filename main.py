import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlmodel import Field, Session, SQLModel, create_engine, text

USER = os.getenv("DB_USER", "admin")
PASSWORD = os.getenv("DB_PASSWORD", "secretpassword")
DB_NAME = os.getenv("DB_NAME", "timeseries")
HOST = os.getenv("DB_HOST", "timescaledb")  # Uses Docker service name

DATABASE_URL = f"postgresql://{USER}:{PASSWORD}@{HOST}:5432/{DB_NAME}"
engine = create_engine(DATABASE_URL)

SQLAlchemyInstrumentor().instrument(engine=engine)

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello, telemetry!"}


# Define the Time-Series Data Model
class ServerMetric(SQLModel, table=True):
    __tablename__ = "server_metrics"
    # Timescale relies heavily on timestamps for partitioning
    time: datetime = Field(default_factory=datetime.utcnow, primary_key=True)
    server_id: str
    cpu_utilization: float


# Setup Database and Timescale Hypertable on Startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    # Convert the standard Postgres table into a Timescale Hypertable
    with Session(engine) as session:
        session.exec(
            text(
                "SELECT create_hypertable('server_metrics', 'time', if_not_exists => TRUE);"
            )
        )
        session.commit()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id, "status": "Found"}


@app.post("/metrics/")
def record_metric(metric: ServerMetric):
    with Session(engine) as session:
        session.add(metric)
        session.commit()
    return {"status": "Metric recorded successfully"}


FastAPIInstrumentor.instrument_app(app)
