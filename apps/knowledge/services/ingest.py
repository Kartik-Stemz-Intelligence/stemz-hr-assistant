import json
import os
from pathlib import Path

import numpy as np
from django.conf import settings

from .parser import parse_document
from .embedder import embed_batch


def _authoritative_path(doc_path):
    path = Path(doc_path).resolve()
    source_root = settings.KNOWLEDGE_DIR.resolve()
    if path.parent != source_root:
        raise ValueError(f'Knowledge files must come directly from {source_root}')
    return path


def _chunks_and_embeddings(doc_path):
    """Parse one supported document into chunks + embeddings (no writes)."""
    doc_path = _authoritative_path(doc_path)
    metadata, chunks = parse_document(doc_path)
    if not chunks:
        raise ValueError(f'No chunks found in {doc_path} — check that it has ## headings.')
    texts = [f"{c['title']}\n\n{c['text']}" for c in chunks]
    embeddings = embed_batch(texts)
    return chunks, embeddings


def _persist(chunks, embeddings_matrix):
    """Write chunks + embeddings atomically so a crash mid-write can't leave the
    two stores out of sync. Each file is written to a temp path then renamed.
    """
    chunks_path = settings.DATA_DIR / 'chunks.json'
    emb_path = settings.DATA_DIR / 'embeddings.npy'

    tmp_chunks = chunks_path.with_name(chunks_path.name + '.tmp')
    tmp_emb = emb_path.with_name(emb_path.name + '.tmp')

    tmp_chunks.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding='utf-8')
    # Pass a file handle so np.save doesn't append its own .npy to the temp name.
    with open(tmp_emb, 'wb') as f:
        np.save(f, embeddings_matrix)

    os.replace(tmp_chunks, chunks_path)
    os.replace(tmp_emb, emb_path)


def ingest_document(doc_path):
    """Ingest a SINGLE supported document, overwriting the store.

    Kept for backwards compatibility and tests. For a multi-doc corpus,
    prefer `ingest_all`.
    """
    chunks, embeddings = _chunks_and_embeddings(doc_path)
    _persist(chunks, embeddings)
    return len(chunks)


def ingest_all(knowledge_dir=None, include_md=True, include_pdf=True, include_docx=True):
    """Ingest EVERY .md/.pdf/.docx file in the knowledge directory into one store.

    Returns a dict summary: {n_chunks, n_docs, per_doc: {name: chunk_count}}.
    Chunk IDs are reassigned so they are unique across the corpus.
    """
    if not include_md and not include_pdf and not include_docx:
        raise ValueError('At least one document type must be enabled for ingestion.')

    knowledge_dir = Path(knowledge_dir or settings.KNOWLEDGE_DIR).resolve()
    if knowledge_dir != settings.KNOWLEDGE_DIR.resolve():
        raise ValueError(f'Knowledge files must come from {settings.KNOWLEDGE_DIR.resolve()}')
    doc_files = []
    if include_md:
        doc_files.extend(sorted(knowledge_dir.rglob('*.md')))
    if include_pdf:
        doc_files.extend(sorted(knowledge_dir.rglob('*.pdf')))
    if include_docx:
        doc_files.extend(sorted(knowledge_dir.rglob('*.docx')))
    if not doc_files:
        raise FileNotFoundError(f'No markdown/pdf/docx files found in {knowledge_dir}')

    all_chunks = []
    all_embeddings = []
    per_doc = {}
    global_id = 0

    for doc_path in doc_files:
        chunks, embeddings = _chunks_and_embeddings(doc_path)
        for c in chunks:
            c['id'] = global_id
            global_id += 1
        all_chunks.extend(chunks)
        all_embeddings.append(embeddings)
        per_doc[doc_path.name] = len(chunks)

    embeddings_matrix = np.vstack(all_embeddings)
    _persist(all_chunks, embeddings_matrix)

    return {
        'n_chunks': len(all_chunks),
        'n_docs': len(doc_files),
        'per_doc': per_doc,
    }
