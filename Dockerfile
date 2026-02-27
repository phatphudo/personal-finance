# ── Stage 1: dependency resolver ─────────────────────────────────────────────
# Use the official uv image to resolve & install deps into a virtual env.
# This stage is cached independently — only re-runs when pyproject.toml /
# uv.lock changes, keeping subsequent builds near-instant.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy only the dependency manifests first (maximises cache reuse)
COPY pyproject.toml uv.lock ./

# Install dependencies into /app/.venv with the lock-file, no editable install
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev


# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# Keeps Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    # Point directly at the venv so we don't need to activate it
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY main.py ./
COPY components/ ./components/
COPY gsheets/ ./gsheets/
COPY utils/ ./utils/

# ── Streamlit config ─────────────────────────────────────────────────────────
# Copy only the non-secret config. Secrets are injected at runtime via a
# bind-mount or an env var (see README).
COPY .streamlit/config.toml ./.streamlit/config.toml

EXPOSE 8501

# Healthcheck — Streamlit exposes a /_stcore/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# Run Streamlit.  The --server.* flags override config.toml where needed.
ENTRYPOINT ["streamlit", "run", "main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--server.fileWatcherType=none"]
