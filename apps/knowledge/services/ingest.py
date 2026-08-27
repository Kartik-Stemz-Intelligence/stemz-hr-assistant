import json
from pathlib import Path

import numpy as np
from django.conf import settings

from .parser import parse_markdown
from .embedder import embed_batch


def _chunks_and_embeddings(md_path):
    """Parse one markdown file into chunks + embeddings (no writes)."""
    metadata, chunks = parse_markdown(md_path)
    if not chunks:
        raise ValueError(f'No chunks found in {md_path} — check that it has ## headings.')
    texts = [f"{c['title']}\n\n{c['text']}" for c in chunks]
    embeddings = embed_batch(texts)
    return chunks, embeddings


def _persist(chunks, embeddings_matrix):
    chunks_path = settings.DATA_DIR / 'chunks.json'
    emb_path = settings.DATA_DIR / 'embeddings.npy'
    chunks_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding='utf-8')
    np.save(emb_path, embeddings_matrix)


def ingest_document(md_path):
    """Ingest a SINGLE markdown file, overwriting the store.

    Kept for backwards compatibility and tests. For a multi-doc corpus,
    prefer `ingest_all`.
    """
    chunks, embeddings = _chunks_and_embeddings(md_path)
    _persist(chunks, embeddings)
    return len(chunks)


def ingest_all(knowledge_dir=None):
    """Ingest EVERY .md file in the knowledge directory into a single store.

    Returns a dict summary: {n_chunks, n_docs, per_doc: {name: chunk_count}}.
    Chunk IDs are reassigned so they are unique across the corpus.
    """
    knowledge_dir = Path(knowledge_dir or settings.KNOWLEDGE_DIR)
    md_files = sorted(knowledge_dir.glob('*.md'))
    if not md_files:
        raise FileNotFoundError(f'No markdown files found in {knowledge_dir}')

    all_chunks = []
    all_embeddings = []
    per_doc = {}
    global_id = 0

    for md_path in md_files:
        chunks, embeddings = _chunks_and_embeddings(md_path)
        for c in chunks:
            c['id'] = global_id
            global_id += 1
        all_chunks.extend(chunks)
        all_embeddings.append(embeddings)
        per_doc[md_path.name] = len(chunks)

    embeddings_matrix = np.vstack(all_embeddings)
    _persist(all_chunks, embeddings_matrix)

    return {
        'n_chunks': len(all_chunks),
        'n_docs': len(md_files),
        'per_doc': per_doc,
    }
