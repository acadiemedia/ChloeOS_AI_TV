FROM python:3.11-slim

# Install FFmpeg and SVG rasterizer
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    librsvg2-bin \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

ENV RTMP_URL="rtmp://stream.livepush.io/live/rtmp_0c6e2581584943ec97e7e1104783d429"

CMD ["python3", "-u", "automation/btc_chart_streamer.py"]
