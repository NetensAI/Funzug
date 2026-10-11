FROM python:3.14.7-alpine3.24

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check --requirement /app/requirements.txt
COPY server.py /app/server.py
RUN addgroup -S -g 10001 media && adduser -S -D -H -u 10001 -G media media \
    && mkdir /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
