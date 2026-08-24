FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first for better layer caching
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY agent ./agent

# Leads DB lives here — mount a volume at /app/data in production so leads
# persist across deploys/restarts, or point BVHOMES_DB_PATH at a managed DB
# path if you migrate storage.py to Postgres later.
RUN mkdir -p /app/data
ENV BVHOMES_DB_PATH=/app/data/leads.db

# Agent workers don't listen on an inbound HTTP port for traffic; they poll
# LiveKit for jobs. No EXPOSE needed for the core agent.

# "start" = production worker mode (as opposed to "console" or "dev")
CMD ["uv", "run", "python", "-m", "agent.main", "start"]
