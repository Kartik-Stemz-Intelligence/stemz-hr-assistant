import json
import numpy as np
from django.conf import settings

from apps.knowledge.services.embedder import embed
from apps.rag.services.reranker import rerank


# `mtime` is the chunks.json modification time captured when the cache was
# populated. Any newer mtime (from a fresh `ingest_docs` run) triggers a
# reload — so re-ingesting no longer requires a server restart.
_CACHE = {'chunks': None, 'embeddings': None, 'mtime': None}


def _looks_like_company_overview_query(query):
    q = (query or '').strip().lower()
    return (
        'stemz' in q and
        any(phrase in q for phrase in (
            'what does', 'what is stemz', 'about stemz', 'overview', 'business', 'vertical', 'services',
        ))
    )


def _overview_boost(candidate):
    chunk = candidate.get('chunk') or {}
    title = (chunk.get('title') or '').lower()
    doc = (chunk.get('doc_title') or chunk.get('document') or '').lower()
    bonus = 0.0
    if 'stemz company overview' in doc:
        bonus += 0.02
    if any(token in title for token in ('business', 'vertical', 'service', 'services', 'overview', 'positioning')):
        bonus += 0.05
    return bonus


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
    if settings.SPEED_FIRST_MODE:
        k = min(k, 5)
    chunks, embeddings = _load()
    q_vec = embed(query)
    scores = embeddings @ q_vec
    candidate_pool = settings.RETRIEVAL_CANDIDATE_POOL
    if settings.SPEED_FIRST_MODE:
        candidate_pool = min(candidate_pool, 10)
    pool_size = min(candidate_pool, len(chunks))
    top_indices = np.argsort(scores)[::-1][:pool_size]
    candidates = [
        {'chunk': chunks[i], 'score': float(scores[i])}
        for i in top_indices
    ]
    if _looks_like_company_overview_query(query):
        candidates.sort(key=lambda item: item['score'] + _overview_boost(item), reverse=True)
    if not settings.ENABLE_RERANK:
        for item in candidates:
            item['rerank_score'] = item['score']
        return candidates[:k]
    return rerank(query, candidates, top_k=k)


def clear_cache():
    _CACHE['chunks'] = None
    _CACHE['embeddings'] = None
    _CACHE['mtime'] = None
