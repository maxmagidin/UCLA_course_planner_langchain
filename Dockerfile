FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLANNER_DATABASE_PATH=/app/.data/planner.sqlite3

RUN groupadd --system planner && useradd --system --gid planner --home /app planner
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY --chown=planner:planner . .
COPY --from=frontend-build --chown=planner:planner /build/frontend/dist ./frontend/dist
RUN mkdir -p /app/.data && chown planner:planner /app/.data

USER planner
EXPOSE 8765
VOLUME ["/app/.data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/ready', timeout=3)"

CMD ["python", "-m", "uvicorn", "course_planner.api:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1", "--proxy-headers"]
