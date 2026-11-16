FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app:/app/backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
COPY config/daily-requirements.txt config/daily-requirements.txt
COPY deploy/requirements.txt deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt
RUN useradd --uid 10001 --create-home appuser
COPY --chown=appuser:appuser backend backend
COPY --chown=appuser:appuser pipeline pipeline
COPY --chown=appuser:appuser forecast forecast
COPY --chown=appuser:appuser config config
COPY --chown=appuser:appuser params params
COPY --chown=appuser:appuser tools tools
COPY --chown=appuser:appuser deploy deploy
RUN mkdir -p data dataset outputs backend/cache && chown -R appuser:appuser /app
USER appuser
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --start-period=60s --interval=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
