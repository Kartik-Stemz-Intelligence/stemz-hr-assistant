"""Extract plain text from uploaded documents (PDF / DOCX / TXT / MD).

The extracted text is fed directly into Claude's context — no chunking,
no embedding, no RAG. This is deliberately different from the corpus flow:
uploaded docs are ephemeral per-session context, not vetted policies.

Design constraints:
- File size cap: 10 MB (before extraction)
- Char cap: 60,000 after extraction — well within Claude's 200k context,
  leaves comfortable room for system prompt + conversation history + response
- Scanned PDFs (image-only, no text layer) will extract empty — we surface
  that back to the user rather than silently loading nothing
"""
import io
from pathlib import Path


MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB — before extraction
MAX_CHARS = 60_000                     # ~15k tokens; ~20 pages of typical prose
SUPPORTED_EXTS = ('.pdf', '.docx', '.txt', '.md')


class DocumentError(ValueError):
    """Raised for user-facing extraction problems (bad format, empty, too long)."""


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return plain text extracted from a file's bytes.

    Raises DocumentError with a user-facing message on any problem.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise DocumentError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTS)}"
        )

    # A file renamed to a supported extension can still fail to parse. Convert
    # any extractor exception into a user-facing DocumentError instead of a 500.
    try:
        if ext == '.pdf':
            text = _extract_pdf(file_bytes)
        elif ext == '.docx':
            text = _extract_docx(file_bytes)
        else:  # .txt / .md
            text = file_bytes.decode('utf-8', errors='replace')
    except DocumentError:
        raise
    except Exception:
        raise DocumentError(
            f"Could not read this file as {ext}. Please check it isn't corrupted "
            "and matches its extension."
        )
    text = text.strip()
    if not text:
        raise DocumentError(
            'No text found in the document. If it is a scanned PDF, '
            'this tool cannot read it — please share the original file instead.'
        )
    if len(text) > MAX_CHARS:
        raise DocumentError(
            f'Document is too long ({len(text):,} characters). '
            f'Maximum is {MAX_CHARS:,} — please shorten or split it.'
        )
    return text


def _extract_pdf(data: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=data, filetype='pdf')
    try:
        return '\n'.join(page.get_text() for page in doc)
    finally:
        doc.close()


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return '\n'.join(p.text for p in doc.paragraphs)
