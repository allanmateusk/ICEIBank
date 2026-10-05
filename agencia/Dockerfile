FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=4000

EXPOSE 4000

CMD ["sh", "-c", "exec python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
