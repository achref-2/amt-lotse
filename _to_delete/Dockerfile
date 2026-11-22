# Amt-Lotse online version (Hugging Face Space).
# The app, speech-to-text and read-aloud run here, always on. The AI (Ollama) stays on your PC and is reached
# privately through Tailscale. When the PC is off, the page still works and says that the AI server is off.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Tailscale runs in "userspace" mode: it needs no special rights, which a Space does not give
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscaled /usr/local/bin/tailscale /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    HOME=/home/user \
    PATH="/app/.venv/bin:$PATH"

# Hugging Face runs every Space as user 1000
RUN useradd --create-home --uid 1000 user
WORKDIR /app

# 1) dependencies only (cached as long as pyproject.toml / uv.lock do not change)
COPY --chown=user pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) the project + example letters; socksio lets the AI requests go through Tailscale's SOCKS5 proxy
COPY --chown=user src ./src
COPY --chown=user data ./data
RUN uv sync --frozen --no-dev && uv pip install socksio==1.0.0

COPY --chown=user start.sh ./
RUN mkdir -p voices audio replies && chown -R user /app
USER user

EXPOSE 7860
CMD ["sh", "start.sh"]
