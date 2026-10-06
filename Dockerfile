FROM python:3.11-slim

# Install system dependencies including ffmpeg for audio normalization
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy source code and configuration
COPY src/ src/
COPY openapi.json .
COPY .env.example .

# Create data and media directories
RUN mkdir -p data uploads exports

EXPOSE 8000

ENV PYTHONPATH=/app/src
ENV ENVIRONMENT=production

CMD ["uvicorn", "solfa_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
