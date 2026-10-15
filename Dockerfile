FROM python:3.12-slim

# Полный git-коммит, из которого собран образ (виден в /health и /metrics)
ARG GIT_SHA=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    DB_PATH=/data/notes.db \
    APP_VERSION=${GIT_SHA}

WORKDIR /srv/app

# зависимости отдельным слоем — кэшируются, пока requirements.txt не менялся
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# приложение работает не от root; /data — каталог для базы (volume)
RUN useradd --system --uid 10001 app \
    && mkdir /data \
    && chown app:app /data
USER app

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=3)"

# один процесс с потоками: порт берётся из $PORT (так требуют облачные платформы)
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 app:app"]
