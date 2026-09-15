FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN opentelemetry-bootstrap -a install

# Copy your application code
COPY main.py .

# Start the instrumented application, explicitly binding to 0.0.0.0 
# so Docker can route traffic to it from the host machine.
CMD ["opentelemetry-instrument", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
