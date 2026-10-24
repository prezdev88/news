FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/news-cache \
    TZ=America/Santiago

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc pkg-config libcairo2-dev fonts-liberation2 fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY manana ./manana
RUN mkdir -p /app/output /tmp/news-cache/fontconfig \
    && chmod 1777 /tmp/news-cache /tmp/news-cache/fontconfig

ENTRYPOINT ["python", "-m", "manana"]
