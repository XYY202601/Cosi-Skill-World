FROM python:3.12-slim

WORKDIR /app

# Copy the shared packages first
COPY packages /app/packages

# Copy the application source code
COPY apps/hermes-orchestrator /app/apps/hermes-orchestrator

# Install the application and its dependencies
RUN pip install --no-cache-dir /app/apps/hermes-orchestrator

WORKDIR /app/apps/hermes-orchestrator
EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
