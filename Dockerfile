FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /app

# Install dependencies first so this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Project files (docker-compose bind-mounts src, data and outbox on top of these for easy editing)
COPY src ./src
COPY data ./data

# Non-root user; docker-compose overrides the uid/gid with yours so files in ./outbox stay yours
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/outbox \
    && chown -R app:app /app/outbox
USER app

# Default: run the offline checks (no API key needed)
CMD ["sh", "-c", "python src/test_finance.py && python src/test_agent_plumbing.py && python src/test_llm.py"]
