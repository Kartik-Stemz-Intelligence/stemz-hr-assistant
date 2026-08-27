import os
# Offline-by-default — weights are cached on first download; subsequent runs
# should never touch the network. Prevents DNS/network flakiness from bubbling
# up as noisy retries at startup. See `.env` for the shared setting.
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = 'BAAI/bge-large-en-v1.5'
_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def embed(text):
    """Embed a single string; returns a normalized numpy vector."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return np.asarray(vector, dtype=np.float32)


def embed_batch(texts):
    """Embed a list of strings; returns a normalized numpy matrix (n, dim)."""
    model = _get_model()
    vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype=np.float32)
