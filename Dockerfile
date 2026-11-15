FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/.cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgdk-pixbuf-2.0-0 \
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app
RUN mkdir -p /tmp/.cache/fontconfig /app/staticfiles \
    && chown -R app:app /tmp/.cache /app/staticfiles

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
COPY --chown=app:app docker-entrypoint.sh /usr/local/bin/cabinet-entrypoint
USER app

EXPOSE 8000
