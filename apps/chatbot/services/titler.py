from anthropic import Anthropic
from django.conf import settings


TITLER_MODEL = 'claude-haiku-4-5'
MAX_TITLE_LEN = 120


def generate_title(first_user_message: str, first_bot_response: str) -> str:
    """Generate a short (4-7 word) conversation title using Haiku.

    Falls back to a truncated user message on any error.
    """
    prompt = (
        "Summarize this conversation opening as a concise chat title of "
        "4 to 7 words. Return ONLY the title text — no quotes, no trailing "
        "punctuation, no prefix like 'Title:'.\n\n"
        f"User: {first_user_message.strip()}\n\n"
        f"Assistant: {first_bot_response[:400].strip()}"
    )
    try:
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=TITLER_MODEL,
            max_tokens=30,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = resp.content[0].text if resp.content else ''
        title = _clean(text)
        return title[:MAX_TITLE_LEN] or _fallback(first_user_message)
    except Exception:
        return _fallback(first_user_message)


def _clean(text: str) -> str:
    text = text.strip()
    for wrap in ('"', "'", '“', '”', '‘', '’'):
        text = text.strip(wrap)
    text = text.rstrip('.').rstrip('!').rstrip('?').strip()
    for prefix in ('Title:', 'title:', 'Chat title:', 'Summary:'):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    return text


def _fallback(message: str) -> str:
    trimmed = message.strip().replace('\n', ' ')
    return (trimmed[:57] + '…') if len(trimmed) > 60 else trimmed
