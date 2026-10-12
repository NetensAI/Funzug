FROM python:3.12-slim-bookworm
WORKDIR /app
COPY scheduler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY instagram_credentials.py /app/
COPY scripts/renew_instagram_credential.py /app/scripts/
COPY scheduler/runner.py /app/scheduler/
USER 1000:1000
CMD ["python", "-m", "scheduler.runner"]
