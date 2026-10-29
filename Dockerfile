FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CCM_DB=/data/ccm.sqlite3 CCM_IMAGE_ROOT=/images
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -g 10001 ccm && useradd -u 10001 -g ccm -m ccm && mkdir /data /images && chown ccm:ccm /data
COPY --chown=ccm:ccm app ./app
COPY --chown=ccm:ccm static ./static
USER ccm
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
