FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PORT=8080 \
    # The model downloads at startup. `useradd --system` does not create
    # /home/svc, so the default ~/.cache/huggingface is unwritable; point
    # the cache inside /app, which svc owns.
    HF_HOME=/app/.hf-cache
EXPOSE 8080

# Non-root: matches the byt5-restorer service. Cuts blast radius if a
# request handler is exploited.
RUN groupadd --system svc && useradd --system --gid svc -d /app svc && \
    mkdir -p ${HF_HOME} && chown -R svc:svc /app
USER svc

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
