"""Fast, hermetic unit tests for pure service helpers.

No network, no LLM, no database — these exercise parsing, guardrail, document
extraction, and titler formatting logic in isolation. Django is configured by
tests/conftest.py before these import.
"""
import pytest

from apps.knowledge.services.parser import _parse_frontmatter, _chunk_base
from apps.knowledge.services import parser as knowledge_parser
from apps.rag.services.guardrail import should_refuse, is_confidential
from apps.chatbot.services.document import extract_text, DocumentError, MAX_CHARS
from apps.chatbot.services.titler import _clean, _fallback
from apps.chatbot import views as chatbot_views


# ----------------------------- Frontmatter parsing -----------------------------

def test_parse_frontmatter_basic_key_values():
    meta = _parse_frontmatter('title: Attendance Policy\nversion: 2')
    assert meta['title'] == 'Attendance Policy'
    assert meta['version'] == '2'


def test_parse_frontmatter_handles_colon_in_value():
    # The old naive splitter kept everything after the first colon, but a quoted
    # YAML value with its own colon must survive intact.
    meta = _parse_frontmatter('note: "see clause 4:30 for details"')
    assert meta['note'] == 'see clause 4:30 for details'


def test_parse_document_dispatches_markdown(monkeypatch):
    called = {'md': False}

    def fake_parse_markdown(path):
        called['md'] = True
        return {'_filename': 'x.md'}, [{'id': 0, 'title': 'A', 'text': 'B'}]

    monkeypatch.setattr(knowledge_parser, 'parse_markdown', fake_parse_markdown)
    metadata, chunks = knowledge_parser.parse_document('x.md')

    assert called['md'] is True
    assert metadata['_filename'] == 'x.md'
    assert chunks[0]['title'] == 'A'


def test_parse_document_dispatches_pdf(monkeypatch):
    called = {'pdf': False}

    def fake_parse_pdf(path):
        called['pdf'] = True
        return {'_filename': 'x.pdf'}, [{'id': 0, 'title': 'A', 'text': 'B'}]

    monkeypatch.setattr(knowledge_parser, 'parse_pdf', fake_parse_pdf)
    metadata, chunks = knowledge_parser.parse_document('x.pdf')

    assert called['pdf'] is True
    assert metadata['_filename'] == 'x.pdf'
    assert chunks[0]['title'] == 'A'


def test_parse_document_rejects_unsupported_extension():
    with pytest.raises(ValueError):
        knowledge_parser.parse_document('x.docx')


def test_chunk_base_confidential_true():
    base = _chunk_base({'title': 'Exec Pay', 'confidential': 'true'})
    assert base['confidential'] is True
    assert base['doc_title'] == 'Exec Pay'


def test_chunk_base_confidential_default_false():
    base = _chunk_base({'title': 'Attendance'})
    assert base['confidential'] is False


# ------------------------------- Guardrail -------------------------------------

def test_should_refuse_below_threshold(monkeypatch):
    from django.conf import settings as dj_settings
    monkeypatch.setattr(dj_settings, 'SIM_THRESHOLD', 0.05)
    assert should_refuse(0.01) is True
    assert should_refuse(0.9) is False


def test_is_confidential():
    assert is_confidential({'confidential': True}) is True
    assert is_confidential({'confidential': False}) is False
    assert is_confidential(None) is False
    assert is_confidential({}) is False


# --------------------------- Document extraction -------------------------------

def test_extract_text_plaintext():
    assert extract_text(b'Hello world', 'note.txt') == 'Hello world'


def test_extract_text_unsupported_extension():
    with pytest.raises(DocumentError):
        extract_text(b'data', 'malware.exe')


def test_extract_text_empty_raises():
    with pytest.raises(DocumentError):
        extract_text(b'   ', 'blank.txt')


def test_extract_text_too_long_raises():
    with pytest.raises(DocumentError):
        extract_text(b'a' * (MAX_CHARS + 1), 'big.txt')


def test_extract_text_corrupt_pdf_is_document_error():
    # Not a real PDF — the extractor must surface a DocumentError, not a 500.
    with pytest.raises(DocumentError):
        extract_text(b'not a pdf', 'fake.pdf')


# ------------------------------- Titler ----------------------------------------

def test_clean_strips_quotes_and_prefix():
    assert _clean('"Title: Leave balance question"') == 'Leave balance question'


def test_clean_removes_trailing_punctuation():
    assert _clean('Attendance rules?') == 'Attendance rules'


def test_fallback_truncates_long_message():
    long = 'x' * 100
    out = _fallback(long)
    assert out.endswith('…')
    assert len(out) <= 61


def test_fallback_summarizes_common_hr_topic():
    out = _fallback('How many late arrivals are allowed per month?')
    assert out == 'Late Arrival Policy'


def test_fallback_uses_assistant_context_when_helpful():
    out = _fallback('Tell me about WFH', 'You can take 1 WFH day per month with 2 days notice.')
    assert out == 'WFH Policy'


def test_maybe_generate_title_uses_titler_service(monkeypatch):
    class DummyConversation:
        pk = 42
        title = ''
        saved_fields = None

        def save(self, update_fields=None):
            self.saved_fields = update_fields

    conv = DummyConversation()

    monkeypatch.setattr(
        chatbot_views,
        'generate_title',
        lambda user_msg, bot_msg: 'Variable Pay Clarification',
    )

    chatbot_views._maybe_generate_title(
        conv,
        is_first_exchange=True,
        user_msg='Am I eligible for variable pay if I resign?',
        bot_msg='Policy details go here.',
    )

    assert conv.title == 'Variable Pay Clarification'
    assert conv.saved_fields == ['title', 'updated_at']


def test_maybe_generate_title_falls_back_to_conversation_id(monkeypatch):
    class DummyConversation:
        pk = 7
        title = ''

        def save(self, update_fields=None):
            return None

    conv = DummyConversation()

    monkeypatch.setattr(chatbot_views, 'generate_title', lambda user_msg, bot_msg: '   ')

    chatbot_views._maybe_generate_title(
        conv,
        is_first_exchange=True,
        user_msg='Question',
        bot_msg='Answer',
    )

    assert conv.title == 'Conversation #7'
