# Multi-stage build zeby zmiescic sie w 256MB Fly.io VM
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---------- runtime ----------
FROM python:3.11-slim

# Non-root user
RUN useradd -m -u 1000 bot
WORKDIR /app

# Copy python deps from builder
COPY --from=builder /root/.local /home/bot/.local
ENV PATH=/home/bot/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy bot source
COPY --chown=bot:bot . /app

USER bot

CMD ["python", "-u", "bot.py"]
