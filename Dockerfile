# Build the Vue application in a dedicated stage so Node.js and source tooling stay out of the runtime image.
# Public ECR mirrors the Docker Official Image and avoids Docker Hub connectivity issues seen on the build host.
FROM public.ecr.aws/docker/library/node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS frontend-builder

WORKDIR /build/frontend

# Copy lock metadata first because dependency layers should remain cacheable when only application code changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Run the frontend tests before building so a broken visitor bundle cannot become a competition artifact.
RUN npm run test && npm run build


# Use Debian slim for broad amd64 compatibility while keeping the exported image reasonably small.
# The digest pins the exact official Python base used for the competition artifact.
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REDIS_ENABLED=false \
    KG_ENABLED=false

WORKDIR /app

# Install explicit runtime dependencies because pyproject.toml currently declares only the optional subset.
COPY requirements-docker.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip setuptools \
    && python -m pip install --no-cache-dir -r requirements-docker.txt

COPY pyproject.toml ./
COPY src/ ./src/

# Editable installation preserves the repository-backed src path because the application resolves frontend assets from it.
RUN python -m pip install --no-cache-dir --no-deps -e .

COPY scripts/ ./scripts/
COPY prompt/ ./prompt/
COPY config/ ./config/
COPY docs/ ./docs/
COPY data/ ./data/
COPY qdrant_db/ ./qdrant_db/
COPY frontend/ ./frontend/
COPY --from=frontend-builder /build/frontend/dist/ ./frontend/dist/

# A dedicated unprivileged account limits container impact while retaining write access to persistent application data.
RUN groupadd --system lingjing \
    && useradd --system --create-home --uid 10001 --gid lingjing lingjing \
    && mkdir -p /app/logs /app/reports/qa_eval \
    && chown -R lingjing:lingjing /app

USER lingjing

EXPOSE 8000

# Probe the page served by FastAPI using the standard library so the runtime image needs no extra diagnostic package.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/visitor', timeout=3).read(1)" || exit 1

STOPSIGNAL SIGTERM

# One worker is mandatory because the embedded Qdrant directory cannot be shared safely by multiple processes.
CMD ["python", "-m", "uvicorn", "lingjing_ai.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
