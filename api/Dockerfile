FROM python:3.11-slim-bookworm

# pyodbc needs the Microsoft ODBC Driver 18 for SQL Server (used in main.py
# and services/sql_export.py) plus build tools to compile pyodbc itself.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg2 g++ gcc unixodbc-dev \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get purge -y curl gnupg2 \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python fully buffers stdout when it isn't attached to a real terminal (the
# normal case in a container), so print()/logging output can sit in an
# internal buffer and never reach `docker logs`/Container Apps Log stream at
# all for a low-traffic process. Force unbuffered output so every print()
# actually shows up in real time.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1


# 90s: enough for a local-model attempt (up to 7s, see LOCAL_MODEL_TIMEOUT_SECONDS
# in main.py) plus a full Claude fallback afterward, with margin. gunicorn's
# default (30s) raced with our own 30s local-model read timeout -- when the
# local model was slow, gunicorn SIGKILLed the worker before either our
# timeout fired or the Claude fallback ever ran, surfacing as a raw
# connection reset ("Failed to fetch") client-side instead of a clean error.
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "90"]
