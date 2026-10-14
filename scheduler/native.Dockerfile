FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY scheduler/native-requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY instagram_credentials.py /app/
COPY scripts/renew_instagram_credential.py /app/scripts/
COPY scripts/reviewed_media.py scripts/validate_ordered_media.py /app/scripts/
COPY scheduler/ /app/scheduler/
USER 1000:1000
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 CMD ["python", "-m", "scheduler.native_health"]
CMD ["python", "-m", "scheduler.native_runner"]
