FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PORT=8080
EXPOSE 8080

# Non-root: matches the byt5-restorer service. Cuts blast radius if a
# request handler is exploited.
RUN groupadd --system svc && useradd --system --gid svc svc
USER svc

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
