FROM python:3.12-slim

WORKDIR /app

# Singapore is a fixed UTC+8 offset in this app, so the image does not install
# tzdata. The process stays small and scales to zero on Cloud Run.
COPY hackheat ./hackheat
COPY data ./data
COPY static ./static
COPY flows ./flows
COPY agents ./agents

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HACKHEAT_HOST=0.0.0.0

EXPOSE 8080

CMD ["python", "-m", "hackheat.http_api"]
