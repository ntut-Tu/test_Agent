FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
ARG AGENT_UID=1000
ARG AGENT_GID=1000
RUN groupadd --gid "$AGENT_GID" agent && useradd --uid "$AGENT_UID" --gid agent --no-create-home agent \
    && mkdir -p /data && chown agent:agent /data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENT_VALUES=/app/values.yaml
USER agent
EXPOSE 8080
CMD ["uvicorn", "codebase_analysis.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-proxy-headers"]
