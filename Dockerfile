FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY . .

FROM python:3.12-slim

WORKDIR /app

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Copy application code
COPY --from=builder /app /app

EXPOSE 5000

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:5000/ || exit 1

RUN useradd -m appuser

# Give appuser ownership of app files
RUN chown -R appuser:appuser /app

USER appuser

CMD ["python", "app.py"]