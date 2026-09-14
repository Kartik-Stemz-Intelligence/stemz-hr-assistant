"""Generate a PDF report documenting the hardening changes made to the
Stemz HR Assistant. Output: reports/stemz-hr-hardening-changes.pdf

Run:  python scripts/make_changes_report.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, ListFlowable, ListItem,
)


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
INK = colors.HexColor('#1a1a1a')
MUTED = colors.HexColor('#6b7280')
ACCENT = colors.HexColor('#111827')
CODE_BG = colors.HexColor('#f5f5f5')
CODE_BORDER = colors.HexColor('#e0e0e0')
HIGH = colors.HexColor('#c2410c')     # orange — high priority
MED = colors.HexColor('#b45309')      # amber — medium
LOW = colors.HexColor('#15803d')      # green — low

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'DocTitle', parent=styles['Title'], fontName='Helvetica-Bold',
    fontSize=26, leading=30, textColor=ACCENT, spaceAfter=6,
)
subtitle_style = ParagraphStyle(
    'DocSubtitle', parent=styles['Normal'], fontName='Helvetica',
    fontSize=12, leading=16, textColor=MUTED, spaceAfter=4,
)
h1 = ParagraphStyle(
    'H1', parent=styles['Heading1'], fontName='Helvetica-Bold',
    fontSize=16, leading=20, textColor=ACCENT, spaceBefore=14, spaceAfter=8,
)
h2 = ParagraphStyle(
    'H2', parent=styles['Heading2'], fontName='Helvetica-Bold',
    fontSize=12.5, leading=16, textColor=INK, spaceBefore=12, spaceAfter=4,
)
label_style = ParagraphStyle(
    'Label', parent=styles['Normal'], fontName='Helvetica-Bold',
    fontSize=9.5, leading=13, textColor=ACCENT, spaceAfter=1,
)
body = ParagraphStyle(
    'Body', parent=styles['Normal'], fontName='Helvetica',
    fontSize=10, leading=15, textColor=INK, alignment=TA_LEFT, spaceAfter=6,
)
where_style = ParagraphStyle(
    'Where', parent=styles['Normal'], fontName='Helvetica-Oblique',
    fontSize=9, leading=13, textColor=MUTED, spaceAfter=6,
)
code_style = ParagraphStyle(
    'Code', parent=styles['Code'], fontName='Courier',
    fontSize=8.5, leading=12, textColor=INK,
)
bullet_style = ParagraphStyle(
    'Bullet', parent=body, fontSize=10, leading=14, spaceAfter=2,
)


def hr():
    return HRFlowable(width='100%', thickness=0.6, color=CODE_BORDER,
                      spaceBefore=6, spaceAfter=10)


def code_block(text):
    """Monospace code snippet inside a subtle grey box."""
    safe = (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace(' ', '&nbsp;').replace('\n', '<br/>'))
    para = Paragraph(safe, code_style)
    tbl = Table([[para]], colWidths=[165 * mm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CODE_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, CODE_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return tbl


def change(flow, title, where, why, code=None, note=None):
    """One change entry: heading, file location, explanation, optional code."""
    flow.append(Paragraph(title, h2))
    flow.append(Paragraph(f'Where: {where}', where_style))
    flow.append(Paragraph('<b>Why &amp; what:</b> ' + why, body))
    if code:
        flow.append(code_block(code))
        flow.append(Spacer(1, 4))
    if note:
        flow.append(Paragraph('<b>Note:</b> ' + note, body))
    flow.append(Spacer(1, 2))


def section(flow, color, tag, heading):
    band = Table([[Paragraph(f'<font color="white"><b>{tag}</b></font>', body)]],
                 colWidths=[28 * mm])
    band.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    flow.append(Spacer(1, 6))
    flow.append(band)
    flow.append(Paragraph(heading, h1))
    flow.append(hr())


# --------------------------------------------------------------------------- #
# Build document
# --------------------------------------------------------------------------- #
def build(out_path):
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title='Stemz HR Assistant — Hardening Changes',
        author='Engineering',
    )
    flow = []

    # ---- Cover ----
    flow.append(Spacer(1, 30))
    flow.append(Paragraph('Stemz HR Assistant', title_style))
    flow.append(Paragraph('Security &amp; Robustness Hardening — Change Report', subtitle_style))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph('A detailed record of what changed, why it changed, and where — '
                          'organised by priority. Architecture was left unchanged; the '
                          'three-app RAG pipeline (knowledge \u2192 rag \u2192 chatbot) is identical.',
                          body))
    flow.append(Spacer(1, 10))
    meta = Table([
        ['Date', 'August 2026'],
        ['Scope', 'High / Medium / Low priority fixes (no architecture change)'],
        ['Validation', 'Django check clean \u00b7 14 new unit tests pass \u00b7 62 retrieval baseline tests pass'],
    ], colWidths=[30 * mm, 135 * mm])
    meta.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 9.5),
        ('FONT', (1, 0), (1, -1), 'Helvetica', 9.5),
        ('TEXTCOLOR', (0, 0), (0, -1), ACCENT),
        ('TEXTCOLOR', (1, 0), (1, -1), INK),
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, CODE_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    flow.append(meta)
    flow.append(Spacer(1, 16))

    # ---- Summary table ----
    flow.append(Paragraph('At a glance', h2))
    summary = Table([
        ['Priority', 'Area', 'Files touched'],
        ['High', 'Settings hardening', 'config/settings/base.py'],
        ['High', 'CSRF protection restored', 'views.py, chat.html'],
        ['High', 'Input validation & rate limiting', 'views.py'],
        ['Medium', 'Thread-safe model caches', 'embedder.py, reranker.py'],
        ['Medium', 'Atomic ingest writes', 'ingest.py'],
        ['Medium', 'Real YAML frontmatter parsing', 'parser.py'],
        ['Medium', 'LLM timeouts & filename escaping', 'generate.py, titler.py'],
        ['Medium', 'Document extraction guard', 'document.py'],
        ['Low', 'Config & dependency hygiene', '.env.example, requirements.txt'],
        ['Low', 'Unit tests & markers', 'tests/test_units.py, pytest.ini'],
    ], colWidths=[22 * mm, 68 * mm, 75 * mm])
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 8.5),
        ('TEXTCOLOR', (0, 1), (0, 3), HIGH),
        ('TEXTCOLOR', (0, 4), (0, 8), MED),
        ('TEXTCOLOR', (0, 9), (0, 10), LOW),
        ('FONT', (0, 1), (0, -1), 'Helvetica-Bold', 8.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
        ('GRID', (0, 0), (-1, -1), 0.4, CODE_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    flow.append(summary)
    flow.append(PageBreak())

    # ================= HIGH PRIORITY =================
    section(flow, HIGH, 'HIGH', 'High priority — security & correctness')

    change(
        flow,
        '1. ALLOWED_HOSTS no longer breaks production',
        'config/settings/base.py',
        'Previously ALLOWED_HOSTS was <font face="Courier">[\'*\'] if DEBUG else []</font>. '
        'The moment DEBUG=False (i.e. production), the list became empty and Django rejected '
        '<b>every</b> request with HTTP 400 — a self-inflicted outage. It now reads a '
        'comma-separated list of real hostnames from an environment variable in production, '
        'which is how Django is designed to be configured.',
        code="ALLOWED_HOSTS = (\n    ['*'] if DEBUG\n    else [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]\n)",
    )
    change(
        flow,
        '2. Fail loudly on insecure SECRET_KEY in production',
        'config/settings/base.py',
        'The SECRET_KEY signs session cookies, CSRF tokens and password-reset tokens. If it '
        'silently fell back to the shipped <font face="Courier">django-insecure-\u2026</font> default, '
        'anyone reading the source could forge those. Django gives no warning — it just runs '
        'insecurely. We now raise ImproperlyConfigured at startup so the misconfiguration is '
        'impossible to miss. This is a no-op in dev (DEBUG=True).',
        code="if not DEBUG and SECRET_KEY == _INSECURE_SECRET_KEY:\n    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set ... when DJANGO_DEBUG=False.')",
    )
    change(
        flow,
        '3. Reject the default admin password in production',
        'config/settings/base.py',
        'The /dashboard/ route is protected by HTTP Basic Auth, but the password defaulted to '
        '<font face="Courier">change-me</font>. A guessable default on an admin surface is '
        'effectively no authentication. The same startup guard now forces a real value in production.',
        code="if not DEBUG and ADMIN_PASSWORD in ('', 'change-me'):\n    raise ImproperlyConfigured('ADMIN_PASSWORD must be set ... when DJANGO_DEBUG=False.')",
    )
    change(
        flow,
        '4. Production security flags (cookies, HSTS, SSL)',
        'config/settings/base.py',
        'Added Django\u2019s standard production hardening: secure-only cookies, HSTS to prevent '
        'protocol downgrade, and no MIME sniffing. Everything is gated behind '
        '<font face="Courier">not DEBUG</font> so local http development is unaffected. '
        'The SSL redirect and HSTS max-age are env-overridable for setups that terminate TLS at a proxy.',
        code="if not DEBUG:\n    SESSION_COOKIE_SECURE = True\n    CSRF_COOKIE_SECURE = True\n    SECURE_CONTENT_TYPE_NOSNIFF = True\n    SECURE_SSL_REDIRECT = ...\n    SECURE_HSTS_SECONDS = ...",
    )

    flow.append(Spacer(1, 4))
    change(
        flow,
        '5. CSRF protection restored on all endpoints',
        'apps/chatbot/views.py + apps/chatbot/templates/chatbot/chat.html',
        'This was the biggest gap. Every state-changing endpoint carried @csrf_exempt. Because '
        'the browser auto-attaches the session cookie to any request to your domain, a malicious '
        'page a signed-in user visits could silently POST to these endpoints as that user \u2014 '
        'deleting conversations or firing off Ask-HR emails. Session-key isolation does not help, '
        'because the victim\u2019s own cookie is what gets abused. The fix has three parts that must '
        'work together: (a) @ensure_csrf_cookie on the page view sets the csrftoken cookie; '
        '(b) all six @csrf_exempt decorators removed, re-enabling Django\u2019s CSRF middleware; '
        '(c) a csrfHeaders() helper in the frontend attaches the X-CSRFToken header to all seven '
        'mutating fetch() calls. Django validates the header against the cookie (double-submit), '
        'which a cross-site attacker cannot read.',
        code="// frontend helper\nfunction csrfHeaders(extra) {\n  return Object.assign({ 'X-CSRFToken': getCookie('csrftoken') }, extra || {});\n}",
    )
    change(
        flow,
        '6. Input validation & rate limiting',
        'apps/chatbot/views.py',
        'Three abuse vectors were open. (a) Chat messages were unbounded \u2014 a multi-megabyte '
        'paste would be embedded and sent to Claude, spiking cost and latency (denial-of-wallet); '
        'now capped at 5,000 characters. (b) The Ask-HR email was only stripped, never validated; '
        'it now passes through Django\u2019s validate_email. (c) Nothing throttled the endpoints \u2014 '
        'chat spam (LLM cost), transcribe spam (CPU-heavy Whisper) and Ask-HR spam (flooding HR). '
        'A lightweight per-session cache-backed rate limiter now guards them with generous limits '
        '(30/min chat, 20/min upload & transcribe, 5/min ask-hr). No new dependency was added.',
        code="@_rate_limit('chat', limit=30, window_s=60)\n...\nif len(query) > MAX_QUERY_CHARS:      # 5000\n    return JsonResponse({'error': 'Message too long...'}, status=400)",
    )
    change(
        flow,
        '7. Stop leaking internal errors to clients',
        'apps/chatbot/views.py (transcribe_audio)',
        'The transcription handler returned the raw exception string to the browser, which can '
        'expose file paths, model names or internal state. The detail now stays server-side and '
        'the user receives a generic message.',
        code="except Exception:\n    return JsonResponse({'error': 'Transcription failed. Please try again.'}, status=500)",
    )

    flow.append(PageBreak())

    # ================= MEDIUM PRIORITY =================
    section(flow, MED, 'MEDIUM', 'Medium priority — robustness')

    change(
        flow,
        '8. Thread-safe model caches',
        'apps/knowledge/services/embedder.py, apps/rag/services/reranker.py',
        'The embedding and reranker models are cached in a module global and lazy-loaded on first '
        'use. Under a threaded server, two concurrent first-requests could each see the cache empty '
        'and both load the (large) model, doubling memory and racing on assignment. Added '
        'double-checked locking \u2014 a cheap check first, a lock only on the cold path, then a '
        're-check inside the lock. This matches the pattern already used in asr.py.',
        code="if _MODEL is None:\n    with _LOCK:\n        if _MODEL is None:\n            _MODEL = SentenceTransformer(MODEL_NAME)",
    )
    change(
        flow,
        '9. Reranker degrades gracefully instead of 500-ing',
        'apps/rag/services/reranker.py',
        'If the cross-encoder failed (out-of-memory, corrupt weights) the whole request used to '
        'error out. It now falls back to the first-stage cosine ordering, so the user gets a '
        'slightly less-optimal answer rather than a failure.',
        code="try:\n    scores = model.predict(pairs)\nexcept Exception:\n    return retrieved[:top_k]",
    )
    change(
        flow,
        '10. Atomic ingest writes',
        'apps/knowledge/services/ingest.py',
        'Retrieval depends on chunks.json and embeddings.npy staying in lockstep \u2014 row i of the '
        'matrix must match chunk i. The old code wrote them sequentially in place, so a crash or '
        'disk-full between the two writes left them desynced, silently corrupting every future '
        'answer. We now write to temp files and os.replace them \u2014 an atomic OS-level swap, so '
        'either the whole old pair or the whole new pair is present, never a half-written mix. A '
        'file handle is passed to np.save so it doesn\u2019t append its own .npy to the temp name.',
        code="tmp_chunks.write_text(...)\nwith open(tmp_emb, 'wb') as f:\n    np.save(f, embeddings_matrix)\nos.replace(tmp_chunks, chunks_path)\nos.replace(tmp_emb, emb_path)",
    )
    change(
        flow,
        '11. Real YAML frontmatter parsing',
        'apps/knowledge/services/parser.py',
        'The old parser split each line on the first colon, which breaks on any value containing a '
        'colon (e.g. "see clause 4:30") or quoted strings, silently truncating metadata. It now '
        'uses yaml.safe_load, with the naive splitter kept as a fallback if PyYAML is missing. '
        'safe_load (never load) avoids YAML\u2019s arbitrary-object-construction risk on untrusted input.',
        code="loaded = yaml.safe_load(frontmatter_raw)\nif isinstance(loaded, dict):\n    return {str(k): ('' if v is None else str(v)) for k, v in loaded.items()}",
    )
    change(
        flow,
        '12. LLM timeouts & filename escaping',
        'apps/rag/services/generate.py, apps/chatbot/services/titler.py',
        'No timeout meant a hung Anthropic request could pin a server worker indefinitely; enough '
        'of those exhausts the worker pool. Bounded waits (120s generate, 15s titler) let requests '
        'fail cleanly. Separately, the user-controlled uploaded filename was interpolated raw into '
        'an XML-ish tag the model reads \u2014 a filename with a quote or angle bracket could break '
        'the tag; it is now html.escape\u2019d. The titler also now logs its fallback instead of '
        'swallowing the error silently (an invalid API key would otherwise mis-title every chat '
        'forever with no signal).',
        code='client = Anthropic(api_key=..., timeout=LLM_TIMEOUT_S)\n...\nf\'<document filename="{html.escape(filename or "", quote=True)}">\'',
    )
    change(
        flow,
        '13. Document extraction guard',
        'apps/chatbot/services/document.py',
        'A file renamed to .pdf but containing junk (or a genuinely corrupt PDF) raised a '
        'low-level library exception that surfaced as an HTTP 500. Any extractor failure now '
        'becomes a clean, user-facing DocumentError (which the view already turns into a friendly '
        '400). Our own intentional DocumentErrors are re-raised unchanged so their specific '
        'messages survive.',
        code="try:\n    ... extract ...\nexcept DocumentError:\n    raise\nexcept Exception:\n    raise DocumentError('Could not read this file as ...')",
    )

    flow.append(PageBreak())

    # ================= LOW PRIORITY =================
    section(flow, LOW, 'LOW', 'Low priority — config, dependencies, tests')

    change(
        flow,
        '14. Complete .env.example',
        '.env.example',
        'It listed only 6 of the ~25 variables the settings actually read. Anyone copying it would '
        'boot with missing email/admin/whisper/model config and hit runtime failures. Every '
        'variable is now documented with its purpose, and which are required in production.',
    )
    change(
        flow,
        '15. Pinned dependencies',
        'requirements.txt',
        'Added upper version bounds (e.g. anthropic>=0.30.0,<1.0) so a future breaking release '
        'cannot silently break a fresh install, and made faster-whisper and PyYAML explicit rather '
        'than assumed to be present.',
    )
    change(
        flow,
        '16. Hermetic unit tests + markers',
        'tests/test_units.py, pytest.ini',
        'The only existing tests covered retrieval. Added 14 fast tests (no network, DB or models) '
        'for the pure logic that changed: frontmatter parsing including the colon-in-value case, '
        'guardrail decisions, document extraction error paths, and titler formatting. They run in '
        '~4 seconds \u2014 cheap regression protection. slow/integration markers were added to '
        'pytest.ini for future organisation.',
    )

    # ---- What was intentionally NOT changed ----
    flow.append(Spacer(1, 8))
    flow.append(Paragraph('Intentionally left unchanged', h2))
    flow.append(Paragraph(
        '<b>is_confidential</b> (guardrail) was <i>not</i> made fail-closed. The instinct is to '
        'treat a missing <font face="Courier">confidential</font> field as confidential \u2014 but '
        'the parser already sets that field on <b>every</b> chunk, so a fail-closed default would '
        'misfire and block all normal, non-confidential policies. The current behaviour is correct '
        'given how chunks are built.', body))

    flow.append(Spacer(1, 10))
    flow.append(hr())
    flow.append(Paragraph(
        'Validation: <b>Django system check</b> reported no issues; <b>14 new unit tests</b> pass; '
        'and the full <b>62-case retrieval baseline</b> still passes \u2014 confirming the reranker '
        'refactor is behaviour-preserving.', body))

    doc.build(flow)


if __name__ == '__main__':
    out_dir = Path(__file__).resolve().parent.parent / 'reports'
    out_dir.mkdir(exist_ok=True)
    out = out_dir / 'stemz-hr-hardening-changes.pdf'
    build(out)
    print(f'Wrote {out}')
