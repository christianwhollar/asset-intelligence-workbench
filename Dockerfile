FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BRICKLINE_DB=/data/brickline.db
WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY src ./src
RUN pip install --no-cache-dir -c constraints.txt . && useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser /data
USER 10001
EXPOSE 8106
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8106/health', timeout=2)"
CMD ["uvicorn", "brickline.container:app", "--host", "0.0.0.0", "--port", "8106"]
