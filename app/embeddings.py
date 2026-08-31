import logging
import os

logger = logging.getLogger("tracepulse.embeddings")

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_ticket(title: str, description: str) -> list[float] | None:
    """Embed a ticket as '{title}. {description}' (logs excluded: noisy, low semantic signal)."""
    try:
        text = f"{title}. {description}"
        vec = _get_model().encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception:
        logger.exception("Embedding generation failed; saving ticket without embedding")
        return None