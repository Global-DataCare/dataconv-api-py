FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG GDC_DATA_UTILS_WHEEL_URL=https://github.com/Global-DataCare/gdc-data-utils-py/releases/download/v0.1.0/gdc_data_utils_py-0.1.0-py3-none-any.whl
ARG GDC_DATA_UTILS_WHEEL_SHA256=52ec4e842e3cbde1f2142760b4aba57291eccdb0915a23835bdc098fd2467ec3

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
    curl -fsSL "${GDC_DATA_UTILS_WHEEL_URL}" -o /tmp/gdc_data_utils_py-0.1.0-py3-none-any.whl && \
    echo "${GDC_DATA_UTILS_WHEEL_SHA256}  /tmp/gdc_data_utils_py-0.1.0-py3-none-any.whl" | sha256sum -c - && \
    chmod +x /usr/local/bin/cloud-sql-proxy && \
    chmod +x /app/scripts/*.sh

RUN pip install --upgrade pip setuptools wheel && \
    pip install /tmp/gdc_data_utils_py-0.1.0-py3-none-any.whl && \
    pip install ".[prod]"

EXPOSE 8080

CMD ["/app/scripts/container-entrypoint.sh", "preconversion-api"]
