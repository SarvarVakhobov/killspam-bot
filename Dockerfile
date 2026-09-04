# Python 3.11, not the host's 3.14: aiogram 3.13.0 pins aiohttp<3.11 and
# pydantic<2.9, and neither publishes cp314 wheels. Pinning the interpreter here
# is what lets requirements.txt stay exactly as tested.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: onnxruntime (NudeNet) links against it and slim images omit it.
# curl: container healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps before source, so a code edit doesn't re-resolve the whole tree.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 10001 bot && chown -R bot:bot /app
USER bot

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8090}/health" || exit 1

# Same two steps as the Procfile: migrate, then poll + serve.
CMD ["sh", "-c", "python init_db.py && python -m spam_bot.main"]
