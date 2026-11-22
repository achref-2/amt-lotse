# Amt-Lotse app image. Models run in a separate Ollama container (see docker-compose.yml).
FROM python:3.14-slim

# uv: fast, reproducible installs from uv.lock
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False

WORKDIR /app

# 1) dependencies only (cached as long as pyproject.toml / uv.lock do not change)
# LICENSE is needed for the build: pyproject.toml lists it under license-files
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) the project itself + example letters
COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# no root inside the container
RUN useradd --create-home amt && mkdir -p /app/voices /app/audio /app/replies && chown -R amt /app
USER amt

EXPOSE 7860
# 0.0.0.0 inside the container; docker-compose publishes the port only on 127.0.0.1 of your computer
CMD ["amt-lotse-ui", "--host", "0.0.0.0"]
