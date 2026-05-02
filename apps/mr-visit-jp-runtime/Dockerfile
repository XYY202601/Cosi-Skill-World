FROM python:3.12-slim

WORKDIR /app

# Copy the shared packages first
COPY packages /app/packages

# Copy the application source code
COPY apps/mr-visit-jp-runtime /app/apps/mr-visit-jp-runtime

# Install the application and its dependencies
RUN pip install --no-cache-dir /app/apps/mr-visit-jp-runtime

WORKDIR /app/apps/mr-visit-jp-runtime
EXPOSE 8100

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8100"]
