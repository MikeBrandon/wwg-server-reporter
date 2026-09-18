FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir python-a2s
COPY reporter.py .
# Mount your config at /app/config.json and pass WWG_GS_KEY in the environment.
ENV WWG_REPORTER_CONFIG=/app/config.json
STOPSIGNAL SIGTERM
CMD ["python", "reporter.py"]
