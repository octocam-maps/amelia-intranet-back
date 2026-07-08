# Stage 1: dependencias
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /app/deps -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/deps /app/deps
COPY . .

ENV PYTHONPATH=/app:/app/deps
ENV PATH="/app/deps/bin:$PATH"

EXPOSE 8000

CMD ["python", "run_server.py"]
