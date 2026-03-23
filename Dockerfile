FROM python:3.11-slim

WORKDIR /app

# Install dependencies (including psycopg2 for PostGIS)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy local package and install
COPY . .
RUN pip install --no-cache-dir .[all]

# Run FastAPI server
EXPOSE 8000
CMD ["uvicorn", "openetruscan.server:app", "--host", "0.0.0.0", "--port", "8000"]
