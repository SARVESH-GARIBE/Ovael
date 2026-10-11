# Build context is the repository root (the scanner needs ../dataset_collection):
#   docker build -f backend/Dockerfile --target api .
#
# Targets:
#   api      FastAPI instances and Celery workers (no browser)
#   scanner  isolated website scanner with headless Chromium

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 ovael
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt
COPY backend/ovael /app/backend/ovael
COPY backend/pyproject.toml /app/backend/
WORKDIR /app/backend
ENV OVAEL_MODEL_DIR=/models OVAEL_CRAWLER_PATH=/app/dataset_collection

FROM base AS api
# The website dataset is needed for (re)training the website model.
COPY dataset_collection/output/website_features.csv /app/dataset_collection/output/website_features.csv
ENV OVAEL_WEBSITE_DATASET=/app/dataset_collection/output/website_features.csv
USER ovael
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live')"
CMD ["uvicorn", "ovael.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM base AS scanner
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium && chmod -R a+rX /ms-playwright
COPY dataset_collection/ovael_crawler /app/dataset_collection/ovael_crawler
COPY dataset_collection/reference /app/dataset_collection/reference
USER ovael
EXPOSE 9200
CMD ["uvicorn", "ovael.scanner.service:app", "--host", "0.0.0.0", "--port", "9200"]

FROM base AS defense-agent
RUN apt-get update && apt-get install -y --no-install-recommends iptables && rm -rf /var/lib/apt/lists/*
EXPOSE 9100
CMD ["uvicorn", "ovael.defense.agent:app", "--host", "0.0.0.0", "--port", "9100"]
