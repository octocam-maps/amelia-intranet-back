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
# TZ-1 (auditoría QA Fase 3): fija la hora del proceso a UTC explícitamente
# — no depender de la TZ de la imagen base ni del host. "Qué día es hoy"
# para RRHH (dashboard, fichaje, export) se decide aparte en
# src/shared/utils/timezone.py (Europe/Madrid), no con la hora del sistema.
ENV TZ=UTC

EXPOSE 8000

CMD ["python", "run_server.py"]
