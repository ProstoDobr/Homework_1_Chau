# --- сборка ---------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /srv/app

# ставим зависимости отдельным слоем, чтобы кэшировался при неизменном requirements.txt
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

ENV PORT=8000 \
    DB_PATH=/data/notes.db \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
