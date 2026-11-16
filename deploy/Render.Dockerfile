FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_CESIUM_ION_TOKEN=""
ARG VITE_GOOGLE_MAPS_API_KEY=""
ENV VITE_CESIUM_ION_TOKEN=$VITE_CESIUM_ION_TOKEN VITE_GOOGLE_MAPS_API_KEY=$VITE_GOOGLE_MAPS_API_KEY
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app:/app/backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates openssh-client && rm -rf /var/lib/apt/lists/*
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
COPY --from=frontend --chown=appuser:appuser /frontend/dist /app/frontend/dist
RUN chown appuser:appuser /app
EXPOSE 10000
CMD ["python", "deploy/render_start.py"]
