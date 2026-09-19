FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG GDC_DATA_UTILS_WHEEL_URL=https://github.com/Global-DataCare/gdc-data-utils-py/releases/download/v0.1.1/gdc_data_utils_py-0.1.1-py3-none-any.whl
ARG GDC_DATA_UTILS_WHEEL_SHA256=d1e51f2b30e5f0edfa4c19eeeae769a3bb6cd67ff45b6499a7b193effc39c66e

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
    curl -fsSL "${GDC_DATA_UTILS_WHEEL_URL}" -o /tmp/gdc_data_utils_py-0.1.1-py3-none-any.whl && \
    echo "${GDC_DATA_UTILS_WHEEL_SHA256}  /tmp/gdc_data_utils_py-0.1.1-py3-none-any.whl" | sha256sum -c - && \
    chmod +x /usr/local/bin/cloud-sql-proxy && \
    chmod +x /app/scripts/*.sh

RUN pip install --upgrade pip setuptools wheel && \
    pip install /tmp/gdc_data_utils_py-0.1.1-py3-none-any.whl && \
    pip install ".[prod]"

EXPOSE 8080

CMD ["/app/scripts/container-entrypoint.sh", "preconversion-api"]
