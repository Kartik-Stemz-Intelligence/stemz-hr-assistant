import json
import numpy as np
from django.conf import settings

from apps.knowledge.services.embedder import embed
from apps.rag.services.reranker import rerank


# `mtime` is the chunks.json modification time captured when the cache was
# populated. Any newer mtime (from a fresh `ingest_docs` run) triggers a
# reload — so re-ingesting no longer requires a server restart.
_CACHE = {'chunks': None, 'embeddings': None, 'mtime': None}

CANDIDATE_POOL = 20  # retrieve this many candidates, then rerank to TOP_K


def _load():
    chunks_path = settings.DATA_DIR / 'chunks.json'
    emb_path = settings.DATA_DIR / 'embeddings.npy'
    if not chunks_path.exists() or not emb_path.exists():
        raise FileNotFoundError(
            'Knowledge base not ingested. Run `python manage.py ingest_docs` first.'
        )
    current_mtime = chunks_path.stat().st_mtime
    if _CACHE['chunks'] is None or _CACHE['mtime'] != current_mtime:
        _CACHE['chunks'] = json.loads(chunks_path.read_text(encoding='utf-8'))
        _CACHE['embeddings'] = np.load(emb_path)
        _CACHE['mtime'] = current_mtime
    return _CACHE['chunks'], _CACHE['embeddings']


def retrieve(query, k=None):
    """Two-stage retrieval: cosine similarity for candidates, cross-encoder rerank."""
    if k is None:
        k = settings.TOP_K
    chunks, embeddings = _load()
    q_vec = embed(query)
    scores = embeddings @ q_vec
    pool_size = min(CANDIDATE_POOL, len(chunks))
    top_indices = np.argsort(scores)[::-1][:pool_size]
    candidates = [
        {'chunk': chunks[i], 'score': float(scores[i])}
        for i in top_indices
    ]
    return rerank(query, candidates, top_k=k)


def clear_cache():
    _CACHE['chunks'] = None
    _CACHE['embeddings'] = None
    _CACHE['mtime'] = None
