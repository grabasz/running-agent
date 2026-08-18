FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py db_common.py garmin.py db_read.py db_write.py auth.py ./

ENV TOKEN_DIR=/data/garminconnect
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py", "--transport", "http", "--host", "0.0.0.0"]
