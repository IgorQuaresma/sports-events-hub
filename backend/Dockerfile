FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY app ./app
RUN uv pip install --system --no-cache .

COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
COPY scripts ./scripts

RUN useradd -m -u 1000 appuser && mkdir -p /data/raw && chown -R appuser /data /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
