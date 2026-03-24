FROM python:3.11-slim

WORKDIR /app

# Prevent .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies (including psycopg2 for PostGIS)
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy local package and install
COPY . .
RUN pip install --no-cache-dir .[all]

# Create non-root user
RUN groupadd --system appuser && useradd --system --gid appuser appuser
USER appuser

# Run FastAPI server
EXPOSE 8000
CMD ["uvicorn", "openetruscan.server:app", "--host", "0.0.0.0", "--port", "8000"]
