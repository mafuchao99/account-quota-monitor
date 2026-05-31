FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    CPA_MONITOR_CONFIG=/app/config/config.yaml

COPY pyproject.toml uv.lock README.md README.en.md ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && uv run --frozen playwright install chromium

VOLUME ["/app/config", "/app/data"]

CMD ["sh", "-c", "uv run --frozen cpa-monitor --config ${CPA_MONITOR_CONFIG} run"]
