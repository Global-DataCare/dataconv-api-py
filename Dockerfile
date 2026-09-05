FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build dependencies for optional crypto/compression wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY configs /app/configs
COPY examples /app/examples
COPY scripts /app/scripts
COPY src /app/src

RUN curl -fsSL "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.18.3/cloud-sql-proxy.linux.amd64" -o /usr/local/bin/cloud-sql-proxy && \
    chmod +x /usr/local/bin/cloud-sql-proxy && \
    chmod +x /app/scripts/*.sh

RUN pip install --upgrade pip setuptools wheel && \
    pip install ".[prod]"

EXPOSE 8080

CMD ["/app/scripts/container-entrypoint.sh", "preconversion-api"]
