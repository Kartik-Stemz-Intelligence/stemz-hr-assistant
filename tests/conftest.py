import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

import pytest
from django.conf import settings


@pytest.fixture(scope='session', autouse=True)
def ensure_ingested():
    """Ingest the attendance policy once per test session if not already ingested."""
    chunks_path = settings.DATA_DIR / 'chunks.json'
    emb_path = settings.DATA_DIR / 'embeddings.npy'
    if not chunks_path.exists() or not emb_path.exists():
        from apps.knowledge.services.ingest import ingest_document
        ingest_document(str(settings.KNOWLEDGE_DIR / 'old-knowledge' / 'attendance-policy.md'))
    yield
