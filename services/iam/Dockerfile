FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 kubo \
    && mkdir -p /var/lib/kubo \
    && chown kubo:kubo /var/lib/kubo

ENV KUBO_IAM_DATABASE_URL=sqlite:////var/lib/kubo/iam.db
ENV KUBO_IAM_SERVICE_ROOT=/app
VOLUME ["/var/lib/kubo"]
WORKDIR /var/lib/kubo
USER kubo

EXPOSE 8000
CMD ["uvicorn", "kubo_iam.main:app", "--host", "0.0.0.0", "--port", "8000"]
