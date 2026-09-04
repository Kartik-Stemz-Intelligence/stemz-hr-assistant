import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml ships with our deps
    yaml = None


# Frontmatter fields lifted onto every chunk. `title` from the frontmatter is
# renamed to `doc_title` when copied onto a chunk, because `chunk['title']`
# already means "section heading" (## …) in the retrieval pipeline.
_CHUNK_FIELDS = (
    'document',        # long descriptive name — used in existing chat citations
    'category',
    'version',
    'effective_date',
    'approved_by',
    'signed_on',
    'status',
    'source',
    'department',
)


def parse_markdown(md_path):
    """Parse a markdown file with YAML frontmatter into (metadata, chunks).

    Each ## heading becomes one chunk. Chunk text is the body under that
    heading. Every chunk carries the doc-level metadata below so retriever,
    chat citations, and admin dashboard all read from the same source.
    """
    content = Path(md_path).read_text(encoding='utf-8')
    metadata, body = _split_frontmatter(content)
    metadata['_filename'] = Path(md_path).name  # for the admin dashboard
    chunks = _split_by_heading(body, metadata)
    return metadata, chunks


def _split_frontmatter(content):
    match = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content
    frontmatter_raw, body = match.groups()
    metadata = _parse_frontmatter(frontmatter_raw)
    return metadata, body


def _parse_frontmatter(frontmatter_raw):
    """Parse YAML frontmatter. Prefer a real YAML parser (handles quotes,
    colons in values, typed booleans); fall back to naive line splitting only
    if PyYAML is unavailable or the block isn't a mapping.
    """
    if yaml is not None:
        try:
            loaded = yaml.safe_load(frontmatter_raw)
            if isinstance(loaded, dict):
                return {str(k): ('' if v is None else str(v)) for k, v in loaded.items()}
        except yaml.YAMLError:
            pass
    metadata = {}
    for line in frontmatter_raw.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _chunk_base(metadata):
    """Doc-level metadata copied onto every chunk. `title` frontmatter is
    exposed as `doc_title` to avoid clashing with the section-heading `title`.
    """
    base = {k: metadata[k] for k in _CHUNK_FIELDS if k in metadata}
    base['doc_title'] = metadata.get('title') or metadata.get('document', 'Untitled')
    # Some legacy chunks are missing `document`; backfill from `title` so
    # existing citation code keeps working without a fallback everywhere.
    if 'document' not in base:
        base['document'] = base['doc_title']
    # `confidential: true` in frontmatter flags a document the assistant must
    # never answer from — every chunk carries the boolean for the guardrail.
    base['confidential'] = str(metadata.get('confidential', '')).strip().lower() in ('true', 'yes', '1')
    return base


def _split_by_heading(body, metadata):
    base_meta = _chunk_base(metadata)

    chunks = []
    current_title = None
    current_body = []
    chunk_id = 0

    def flush():
        nonlocal chunk_id
        text = '\n'.join(current_body).strip()
        if current_title is not None and text:
            # base_meta first, then the chunk-specific fields override —
            # so `title` here is the section heading, not the doc title.
            chunk = {**base_meta, 'id': chunk_id, 'title': current_title, 'text': text}
            chunks.append(chunk)
            chunk_id += 1

    for line in body.split('\n'):
        if line.startswith('## '):
            flush()
            current_title = line[3:].strip()
            current_body = []
        elif line.startswith('# '):
            continue
        else:
            current_body.append(line)

    flush()  # final section
    return chunks
