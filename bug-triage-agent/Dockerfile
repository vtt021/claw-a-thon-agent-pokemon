# ── Stage 1: build deps in isolated layer ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Upgrade pip once, then install wheels into a prefix we'll copy later
RUN pip install --upgrade pip --no-cache-dir

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Pull only the installed packages from the builder — no pip, no build tools
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=app:app agent/    ./agent/
COPY --chown=app:app examples/ ./examples/

WORKDIR /app/agent

# Tunable at runtime; default matches your input
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

EXPOSE 8080

USER app

# Healthcheck using stdlib only — no curl/wget needed
HEALTHCHECK --interval=10s --timeout=2s --start-period=5s --retries=3 \
  CMD python -c "\
import sys, urllib.request as u; \
code = u.urlopen('http://127.0.0.1:8080/health', timeout=2).getcode(); \
sys.exit(0 if code == 200 else 1)" || exit 1

# exec-form via sh so $PORT expansion works
CMD ["sh", "-c", "exec uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8080}"]
