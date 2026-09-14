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


def parse_document(path):
    """Parse a supported knowledge document into (metadata, chunks).

    Supported formats:
    - .md   : markdown with optional YAML frontmatter
    - .pdf  : text-first PDFs that may include the same frontmatter block
    - .docx : Word documents that may include the same frontmatter block
    """
    suffix = Path(path).suffix.lower()
    if suffix == '.md':
        return parse_markdown(path)
    if suffix == '.pdf':
        return parse_pdf(path)
    if suffix == '.docx':
        return parse_docx(path)
    raise ValueError(f'Unsupported knowledge document type: {suffix}')


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


def parse_pdf(pdf_path):
    """Parse a PDF into (metadata, chunks) using text extraction.

    The parser expects text PDFs (not scanned image PDFs). If the PDF content
    includes a frontmatter block and `##` headings, chunking behavior matches
    markdown ingestion.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    try:
        # sort=True reconstructs top-to-bottom/left-to-right reading order.
        # Without it, headings placed in banners/side boxes can be emitted
        # AFTER the body text they title (PyMuPDF's default order follows the
        # PDF content stream, not visual position), which silently merges
        # that page's content into the wrong chunk.
        content = '\n'.join(page.get_text(sort=True) for page in doc)
    finally:
        doc.close()

    # Normalize page breaks and mixed newline styles before heading splits.
    content = content.replace('\f', '\n').replace('\r\n', '\n').replace('\r', '\n')
    # Many exported PDFs mark section titles with '■' instead of markdown's
    # '##', and chapter title pages use a numbered ALL-CAPS banner instead
    # (e.g. '02 CORPORATE DRESS CODE POLICY'). Rewriting both as '##' lets the
    # same heading-based chunker apply here, and ensures chapters that have no
    # '■' sub-heading of their own still get a chunk instead of being folded
    # into whichever section happened to be open.
    content = _normalize_pdf_section_markers(content)

    metadata, body = _split_frontmatter(content)
    metadata['_filename'] = Path(pdf_path).name
    chunks = _split_by_heading(body, metadata)
    if not chunks and body.strip():
        base_meta = _chunk_base(metadata)
        chunks = [{
            **base_meta,
            'id': 0,
            'title': base_meta.get('doc_title', 'Document'),
            'text': body.strip(),
        }]
    return metadata, chunks


def parse_docx(docx_path):
    """Parse a Word document (.docx) into (metadata, chunks) using text extraction.

    Extracts text from all paragraphs. If the content includes a frontmatter block
    and `##` headings, chunking behavior matches markdown/PDF ingestion.
    
    Also tracks approximate page numbers for each chunk (estimated ~40 paragraphs per page).
    """
    from docx import Document

    doc = Document(str(docx_path))
    paragraphs_list = doc.paragraphs
    
    # Build content with paragraph tracking for page estimation
    content = '\n'.join(paragraph.text for paragraph in paragraphs_list)
    
    # Store paragraph indices for page number calculation
    # Rough estimate: ~40 paragraphs per page in a typical DOCX
    metadata, body = _split_frontmatter(content)
    metadata['_filename'] = Path(docx_path).name
    metadata['_paragraphs'] = paragraphs_list  # Pass for page tracking
    
    chunks = _split_by_heading(body, metadata)
    if not chunks and body.strip():
        base_meta = _chunk_base(metadata)
        chunks = [{
            **base_meta,
            'id': 0,
            'title': base_meta.get('doc_title', 'Document'),
            'text': body.strip(),
            'page_number': 1,  # Default to first page
        }]
    return metadata, chunks


_PDF_SECTION_MARKER_RE = re.compile(r'^\s*■\s*(.+?)\s*$')
_PDF_CHAPTER_MARKER_RE = re.compile(r'^\D{0,3}\s*(\d{2})\s+(.+)$')


def _pdf_chapter_banner(line):
    """Detect a numbered chapter banner like '02 CORPORATE DRESS CODE POLICY',
    tolerating a leading icon/emoji (e.g. '☕ 09 CAFETERIA FACILITIES') and
    non-ASCII punctuation in the title. Matches only if every letter in the
    title is uppercase, so normal sentences/table rows aren't mistaken for a
    heading.
    """
    match = _PDF_CHAPTER_MARKER_RE.match(line.strip())
    if not match:
        return None
    number, title = match.group(1), match.group(2).strip()
    letters = [ch for ch in title if ch.isalpha()]
    if len(letters) < 4 or not all(ch.isupper() for ch in letters):
        return None
    return f'{number} {title}'


def _normalize_pdf_section_markers(content):
    """Rewrite '■ Heading' and numbered chapter-banner lines as '## Heading'
    so `_split_by_heading` treats them as section boundaries. List bullets
    use '●', not '■', so this only matches real headings.
    """
    lines = []
    for line in content.split('\n'):
        section_match = _PDF_SECTION_MARKER_RE.match(line)
        if section_match:
            lines.append(f'## {section_match.group(1)}')
            continue
        banner = _pdf_chapter_banner(line)
        if banner:
            lines.append(f'## {banner}')
            continue
        lines.append(line)
    return '\n'.join(lines)


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
    # No frontmatter (e.g. a raw exported PDF/DOCX) → fall back to the
    # filename instead of a generic 'Untitled' citation.
    filename_title = Path(metadata.get('_filename', '')).stem or 'Untitled'
    base['doc_title'] = metadata.get('title') or metadata.get('document') or filename_title
    # Some legacy chunks are missing `document`; backfill from `title` so
    # existing citation code keeps working without a fallback everywhere.
    if 'document' not in base:
        base['document'] = base['doc_title']
    # `confidential: true` in frontmatter flags a document the assistant must
    # never answer from — every chunk carries the boolean for the guardrail.
    base['confidential'] = str(metadata.get('confidential', '')).strip().lower() in ('true', 'yes', '1')
    # Track source file for document links in responses
    base['source_file'] = metadata.get('_filename', 'Document')
    base['source_type'] = metadata.get('_filename', '').split('.')[-1].lower()  # .docx, .pdf, .md
    # Default page number (will be overridden for .docx files)
    base['page_number'] = metadata.get('_page_number', 1)
    return base


def _split_by_heading(body, metadata):
    """Split body by ## (main sections) and ### (subsections) for granular chunking.
    
    Each ### becomes its own chunk if it has content. Otherwise, ## sections
    without ### are kept as single chunks. This enables fine-grained retrieval
    while preserving document structure.
    
    Also estimates page numbers based on text position (~2000 chars per page).
    """
    base_meta = _chunk_base(metadata)
    chunks = []
    chunk_id = 0
    
    current_section = None  # ## heading
    current_subsection = None  # ### heading
    current_body = []
    body_start_position = 0  # Track position in body for page calculation
    
    def estimate_page_number(char_position):
        """Estimate page number based on character position (~2000 chars per page)."""
        page = max(1, (char_position // 2000) + 1)
        return page
    
    def flush():
        nonlocal chunk_id
        text = '\n'.join(current_body).strip()
        if current_subsection is not None and text:
            # Use subsection as title if available
            title = f"{current_section} - {current_subsection}" if current_section else current_subsection
            page_num = estimate_page_number(body_start_position)
            chunk = {**base_meta, 'id': chunk_id, 'title': title, 'text': text, 'page_number': page_num}
            chunks.append(chunk)
            chunk_id += 1
        elif current_section is not None and text:
            # Section without subsections
            page_num = estimate_page_number(body_start_position)
            chunk = {**base_meta, 'id': chunk_id, 'title': current_section, 'text': text, 'page_number': page_num}
            chunks.append(chunk)
            chunk_id += 1
    
    for line in body.split('\n'):
        if line.startswith('### '):
            # New subsection — flush previous subsection or section
            flush()
            current_subsection = line[4:].strip()
            current_body = []
            body_start_position += len(line) + 1
        elif line.startswith('## '):
            # New main section — flush previous (sub)section
            flush()
            current_section = line[3:].strip()
            current_subsection = None
            current_body = []
            body_start_position += len(line) + 1
        elif line.startswith('# '):
            # Skip top-level headings
            body_start_position += len(line) + 1
            continue
        else:
            current_body.append(line)
            body_start_position += len(line) + 1
    
    flush()  # final section/subsection
    return chunks
