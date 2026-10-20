FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NIS2_DATA_DIR=/data

WORKDIR /opt/nis2-auditor
COPY pyproject.toml README.md ./
COPY nis2_auditor ./nis2_auditor
RUN pip install --no-cache-dir . \
    && groupadd --system --gid 10001 auditor \
    && useradd --system --uid 10001 --gid auditor --no-create-home auditor \
    && mkdir -p /data \
    && chown auditor:auditor /data

USER auditor
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["nis2-auditor", "serve", "--host", "0.0.0.0", "--port", "8000"]
