FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "yt-dlp[default]" \
    && useradd -r -m gateway && mkdir -p /data && chown gateway /data
WORKDIR /app
COPY fonts/ /app/fonts/
COPY autopilot.py brief_import.py campaign_api.py campaigns.py clip_campaigns.py headline.py hls.py planner.py retention.py stacked.py thumbnail.py gateway.py test_headline.py test_stacked.py test_thumbnail.py test_retention.py ./
USER gateway
EXPOSE 8100
CMD ["python", "-u", "gateway.py"]
