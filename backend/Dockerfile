FROM python:3.14-slim AS builder

COPY pyproject.toml .
RUN pip install --no-cache-dir uv \
    && uv sync --no-dev --frozen

FROM python:3.14-slim
WORKDIR /app
COPY --from=builder /root/.local/share/uv /root/.local/share/uv
COPY --from=builder /root/.cache/uv /root/.cache/uv
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
