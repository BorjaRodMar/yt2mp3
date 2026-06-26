# Imagen multiarch: el Action la compila para ARM64 (tu Pi 5) y amd64.
FROM python:3.12-slim

# FFmpeg: la pieza nativa que convierte a MP3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core.py app.py ./

RUN mkdir -p /app/descargas

EXPOSE 5000

# gunicorn escucha en 0.0.0.0:5000 (lo que apunta APP_PORT del app_proxy).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "600", "app:app"]
