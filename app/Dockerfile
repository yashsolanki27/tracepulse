FROM python:3.12-slim

WORKDIR /app

# Build context is the REPO ROOT (dockerfile: app/Dockerfile) so that
# alembic.ini + migrations/ can be baked in — Alembic is the schema
# source of truth and migrations run at container start (start.sh).
COPY app/requirements.txt app/requirements.txt
# Install CPU-only torch FIRST, from the pytorch CPU index as the sole index,
# so sentence-transformers never pulls GPU wheels from PyPI.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r app/requirements.txt

ENV EMBEDDING_MODEL=all-MiniLM-L6-v2 HF_HOME=/app/hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY alembic.ini ./
COPY migrations ./migrations
COPY app/ .

COPY app/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000
# Railway injects PORT; start.sh falls back to 8000 locally.
CMD ["/start.sh"]
