import os
# Offline-by-default — see embedder.py for full rationale.
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

from sentence_transformers import CrossEncoder


MODEL_NAME = 'BAAI/bge-reranker-v2-m3'
_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = CrossEncoder(MODEL_NAME)
    return _MODEL


def rerank(query, retrieved, top_k):
    """Rerank retrieved chunks using a cross-encoder. Returns top_k."""
    if not retrieved:
        return retrieved
    model = _get_model()
    pairs = [(query, item['chunk']['text']) for item in retrieved]
    scores = model.predict(pairs)
    scored = list(zip(retrieved, scores))
    scored.sort(key=lambda x: x[1], reverse=True)
    result = []
    for item, ce_score in scored[:top_k]:
        item['rerank_score'] = float(ce_score)
        result.append(item)
    return result
