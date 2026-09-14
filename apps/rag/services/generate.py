import html
import re

from anthropic import Anthropic
from django.conf import settings

from apps.rag.prompts.grounding import GROUNDING_SYSTEM_PROMPT, DOCUMENT_SYSTEM_PROMPT


_DETAIL_REQUEST_RE = re.compile(
    r"\b(detail|detailed|elaborate|expand|full explanation|step by step|in depth|deep dive|more context)\b",
    re.IGNORECASE,
)


def _max_tokens_for_query(query):
    """Keep replies concise by default; allow longer answers on explicit request."""
    ceiling = max(128, int(settings.MAX_LLM_TOKENS))
    if _DETAIL_REQUEST_RE.search(query or ''):
        # ~500 words upper bound in practice, constrained by the configured ceiling.
        return min(ceiling, 900)
    return min(ceiling, 260)


def _format_context(retrieved):
    """Format retrieved chunks as numbered excerpts for the LLM."""
    parts = []
    chunk_cap = settings.MAX_CONTEXT_CHARS_PER_CHUNK
    for i, item in enumerate(retrieved, start=1):
        c = item['chunk']
        version = f" (v{c['version']})" if c.get('version') else ''
        excerpt = c['text']
        if chunk_cap > 0 and len(excerpt) > chunk_cap:
            excerpt = excerpt[:chunk_cap].rstrip() + '…'
        
        # Include source file reference for user transparency
        source_file = c.get('source_file', c.get('document', 'Document'))
        source_ref = f"\nSource: {source_file}" if source_file else ''
        
        parts.append(
            f"[{i}] Section: {c['title']}\n"
            f"Document: {c['document']}{version}{source_ref}\n\n"
            f"{excerpt}"
        )
    return '\n\n---\n\n'.join(parts)


def _build_messages(prior_messages, user_message):
    """Convert prior + current messages to Anthropic API format, with a
    cache_control breakpoint on the last prior message.

    Effect: on turn 2+, everything up to (and including) the last prior
    message is cached and re-used across the conversation. New user turn
    is always uncached (it changes every request). No-op on turn 1.
    """
    messages = []
    for i, msg in enumerate(prior_messages or []):
        content_blocks = [{'type': 'text', 'text': msg['content']}]
        if i == len(prior_messages) - 1:  # last prior message → cache breakpoint
            content_blocks[0]['cache_control'] = {'type': 'ephemeral'}
        messages.append({'role': msg['role'], 'content': content_blocks})
    messages.append({'role': 'user', 'content': user_message})
    return messages


def stream_answer(query, retrieved, prior_messages=None, model=None):
    """Stream the grounded answer from Claude, yielding text chunks.

    Args:
        query: The user's current question.
        retrieved: List of retrieved chunks for this query.
        prior_messages: Optional list of prior {role, content} dicts for
            multi-turn continuity when resuming a conversation.
        model: Override for the Claude model. Defaults to CLAUDE_MODEL_DEFAULT.
            The view escalates to CLAUDE_MODEL_ESCALATION for low-confidence
            queries.
    """
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.LLM_TIMEOUT_S)
    context = _format_context(retrieved)
    user_message = (
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {query}"
    )

    messages = _build_messages(prior_messages, user_message)

    # System prompt as a cache-eligible block. If it's under Anthropic's
    # minimum cache size, the flag is silently ignored — no downside.
    system_blocks = [{
        'type': 'text',
        'text': GROUNDING_SYSTEM_PROMPT,
        'cache_control': {'type': 'ephemeral'},
    }]

    with client.messages.stream(
        model=model or settings.CLAUDE_MODEL_DEFAULT,
        max_tokens=_max_tokens_for_query(query),
        system=system_blocks,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def stream_answer_from_document(query, document_text, filename, prior_messages=None, model=None):
    """Stream an answer grounded in a user-uploaded document (no RAG).

    Different from stream_answer:
    - Uses the DOCUMENT_SYSTEM_PROMPT (tuned for single-doc Q&A)
    - Puts the full document text directly in the user message
    - The document is cache-eligible (large static block reused across turns)
    """
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.LLM_TIMEOUT_S)
    doc_text = document_text
    if settings.MAX_DOCUMENT_CONTEXT_CHARS > 0 and len(doc_text) > settings.MAX_DOCUMENT_CONTEXT_CHARS:
        doc_text = doc_text[:settings.MAX_DOCUMENT_CONTEXT_CHARS].rstrip() + '\n\n[Document truncated for speed]'
    user_message = (
        f"<document filename=\"{html.escape(filename or '', quote=True)}\">\n{doc_text}\n</document>\n\n"
        f"Question: {query}"
    )
    messages = _build_messages(prior_messages, user_message)

    system_blocks = [{
        'type': 'text',
        'text': DOCUMENT_SYSTEM_PROMPT,
        'cache_control': {'type': 'ephemeral'},
    }]

    with client.messages.stream(
        model=model or settings.CLAUDE_MODEL_DEFAULT,
        max_tokens=_max_tokens_for_query(query),
        system=system_blocks,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
