from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello, telemetry"}


FastAPIInstrumentor.instrument_app(app)
