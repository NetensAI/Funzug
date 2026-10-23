FROM funzug-native-worker:repair-20261023053035
USER root
COPY funzug_pipeline.py instagram_credentials.py /app/
COPY scripts/ /app/scripts/
COPY scheduler/ /app/scheduler/
COPY home_server/ /app/home_server/
COPY tests/ /app/tests/
USER 1000:1000
CMD ["python", "-m", "home_server.runner"]
