FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# Install CPU-only torch FIRST, from the pytorch CPU index as the sole index,
# so sentence-transformers never pulls GPU wheels from PyPI.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

ENV EMBEDDING_MODEL=all-MiniLM-L6-v2 HF_HOME=/app/hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
