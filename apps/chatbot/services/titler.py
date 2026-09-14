import logging
import re

from anthropic import Anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

TITLER_MODEL = 'claude-haiku-4-5'
MAX_TITLE_LEN = 120
TITLER_TIMEOUT_S = 15

_TITLE_RULES = (
    (re.compile(r'\blate arrivals?\b', re.IGNORECASE), 'Late Arrival Policy'),
    (re.compile(r'\bwork from home\b|\bwfh\b', re.IGNORECASE), 'WFH Policy'),
    (re.compile(r'\bvariable pay\b', re.IGNORECASE), 'Variable Pay'),
    (re.compile(r'\boffice timings?\b|\bstart work\b', re.IGNORECASE), 'Office Timings'),
    (re.compile(r'\battendance\b', re.IGNORECASE), 'Attendance Policy'),
    (re.compile(r'\bsalary band\b|\bcompensation\b', re.IGNORECASE), 'Compensation'),
    (re.compile(r'\bgratuity\b', re.IGNORECASE), 'Gratuity'),
    (re.compile(r'\bconfidential\b', re.IGNORECASE), 'Confidential Policy'),
)

_TITLE_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'can', 'for', 'from', 'how',
    'i', 'in', 'is', 'it', 'many', 'me', 'month', 'of', 'on', 'or', 'per',
    'should', 'tell', 'the', 'to', 'what', 'when', 'where', 'who', 'why',
    'with', 'you', 'your', 'allowed', 'allow', 'need', 'please', 'question',
    'policy', 'policies', 'document', 'documents', 'case', 'this', 'that',
}


def generate_title(first_user_message: str, first_bot_response: str) -> str:
    """Generate a short, intent-based conversation title using Haiku.

    Falls back to a keyword summary rather than echoing the full question.
    """
    prompt = (
        "Write a short chat title that captures the user's intent, not the "
        "exact wording of the question. Prefer a natural noun phrase of 2 to "
        "5 words. Return ONLY the title text, with no quotes and no prefix "
        "like 'Title:'. Avoid copying the question verbatim.\n\n"
        f"User: {first_user_message.strip()}\n\n"
        f"Assistant: {first_bot_response[:400].strip()}"
    )
    try:
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=TITLER_TIMEOUT_S)
        resp = client.messages.create(
            model=TITLER_MODEL,
            max_tokens=30,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = resp.content[0].text if resp.content else ''
        title = _clean(text)
        if _looks_like_echo(title, first_user_message):
            title = ''
        return title[:MAX_TITLE_LEN] or _fallback(first_user_message, first_bot_response)
    except Exception:
        logger.warning('Title generation failed; falling back to keyword summary', exc_info=True)
        return _fallback(first_user_message, first_bot_response)


def _clean(text: str) -> str:
    text = text.strip()
    for wrap in ('"', "'", '“', '”', '‘', '’'):
        text = text.strip(wrap)
    text = text.rstrip('.').rstrip('!').rstrip('?').strip()
    for prefix in ('Title:', 'title:', 'Chat title:', 'Summary:'):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    return text


def _looks_like_echo(title: str, source: str) -> bool:
    source_norm = re.sub(r'\s+', ' ', (source or '')).strip().lower()
    title_norm = re.sub(r'\s+', ' ', (title or '')).strip().lower()
    if not title_norm or not source_norm:
        return False
    return title_norm == source_norm or title_norm in source_norm or source_norm in title_norm


def _fallback(message: str, assistant_response: str = '') -> str:
    for text in (message, assistant_response):
        for pattern, title in _TITLE_RULES:
            if pattern.search(text or ''):
                return title

    summary = _keyword_summary(message or assistant_response or '')
    if summary and len(summary.split()) >= 2:
        return summary[:MAX_TITLE_LEN]

    trimmed = (message or '').strip().replace('\n', ' ')
    return (trimmed[:57] + '…') if len(trimmed) > 60 else (trimmed or 'New chat')


def _keyword_summary(text: str) -> str:
    words = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9']*", text or ''):
        lower = raw.lower()
        if lower in _TITLE_STOPWORDS:
            continue
        if lower == 'wfh':
            words.append('WFH')
        else:
            words.append(raw.capitalize())
        if len(words) >= 4:
            break
    return ' '.join(words).strip()
