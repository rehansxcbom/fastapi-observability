# ==========================================
# Stage 1: Builder (Isolates dependencies in a venv)
# ==========================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

# Create an isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# Stage 2: Runner (Production Image)
# ==========================================
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose the virtual environment binaries to the system PATH
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Create a secure, non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser
USER appuser

# Copy the isolated virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
COPY main.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/docs || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
