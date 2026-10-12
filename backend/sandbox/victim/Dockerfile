# Victim host: a small web server, plus the Ovael flow sensor watching its sandbox interface.
# Build context: backend/ (see docker-compose.yml, profile "sandbox").
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir scapy==2.6.1 httpx==0.28.1
WORKDIR /app
COPY ovael/__init__.py /app/ovael/__init__.py
COPY ovael/feature_extraction /app/ovael/feature_extraction
COPY sandbox/victim/sensor.py /app/sensor.py
COPY sandbox/victim/index.html /var/www/html/index.html
COPY sandbox/victim/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
