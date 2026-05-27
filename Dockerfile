FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CPA_MONITOR_CONFIG=/app/config/config.yaml

COPY pyproject.toml README.md README.en.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install .

VOLUME ["/app/config", "/app/data"]

CMD ["sh", "-c", "cpa-monitor --config ${CPA_MONITOR_CONFIG} run"]
