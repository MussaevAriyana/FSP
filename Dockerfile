FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
# шрифт для PDF-резюме с кириллицей
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh && useradd -r -u 10001 app && mkdir -p /srv/app/storage && chown -R app /srv/app
USER app

ENV DB_PATH=/srv/app/storage/app.db PORT=8000
EXPOSE 8000
VOLUME ["/srv/app/storage"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'))"
ENTRYPOINT ["./docker-entrypoint.sh"]
