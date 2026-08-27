"""Dashboard data service — aggregates chunks.json into per-document rows for
the /dashboard view. Reads directly from the ingest artifact so the dashboard
always reflects what the RAG pipeline actually sees.
"""
import json
from collections import defaultdict, OrderedDict

from django.conf import settings


DOC_ORDER = [
    'Attendance', 'Payroll & Benefits', 'Compliance & Ethics', 'Onboarding',
    'IT & Security', 'Employee Lifecycle', 'Exit', 'Company Info',
]


def load_documents():
    """Return one row per source document, grouped by category.

    Row fields: doc_title, category, version, effective_date, approved_by,
    signed_on, status, source, department, filename, chunk_count.
    """
    chunks_path = settings.DATA_DIR / 'chunks.json'
    if not chunks_path.exists():
        return {'categories': [], 'total_docs': 0, 'total_chunks': 0}

    chunks = json.loads(chunks_path.read_text(encoding='utf-8'))

    per_doc = OrderedDict()  # keyed by doc_title, preserves first-seen order
    for c in chunks:
        key = c.get('doc_title') or c.get('document', 'Untitled')
        if key not in per_doc:
            per_doc[key] = {
                'doc_title': key,
                'category': c.get('category', 'Uncategorized'),
                'version': c.get('version', ''),
                'effective_date': c.get('effective_date', ''),
                'approved_by': c.get('approved_by', ''),
                'signed_on': c.get('signed_on', ''),
                'status': c.get('status', ''),
                'source': c.get('source', ''),
                'department': c.get('department', ''),
                'document': c.get('document', ''),
                'chunk_count': 0,
            }
        per_doc[key]['chunk_count'] += 1

    # Group by category, preserving DOC_ORDER for known ones, others at end.
    by_cat = defaultdict(list)
    for row in per_doc.values():
        by_cat[row['category']].append(row)

    ordered_categories = []
    for cat in DOC_ORDER:
        if cat in by_cat:
            ordered_categories.append((cat, by_cat.pop(cat)))
    for cat in sorted(by_cat.keys()):
        ordered_categories.append((cat, by_cat[cat]))

    return {
        'categories': ordered_categories,
        'total_docs': len(per_doc),
        'total_chunks': len(chunks),
    }
