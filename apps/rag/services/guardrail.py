from django.conf import settings


REFUSAL_MESSAGE = (
    "I don't have that information in the current policy documents. "
    "I'll connect you with HR."
)

CONFIDENTIAL_REFUSAL_MESSAGE = (
    "This question relates to a confidential document that I'm not able to "
    "discuss. Please contact HR directly for assistance with this."
)


def is_confidential(chunk):
    """True if the chunk belongs to a document flagged confidential in its
    frontmatter (`confidential: true`). Such documents must never be answered
    from — the user is redirected to HR instead.
    """
    return bool(chunk and chunk.get('confidential'))


def confidential_hit(retrieved):
    """Return the first retrieved item that belongs to a confidential document
    and is relevant enough to matter, or None.

    Stricter than only inspecting the top result: if a confidential document
    surfaces anywhere in the reranked results with a genuine match score, the
    assistant refuses outright rather than risk answering around it. Uses the
    same SIM_THRESHOLD as `should_refuse` so "relevant enough to answer" and
    "relevant enough to block" stay in lock-step.
    """
    for item in retrieved or []:
        if is_confidential(item.get('chunk')) and item.get('rerank_score', 0.0) >= settings.SIM_THRESHOLD:
            return item
    return None


def should_refuse(top_score):
    """Return True if the top rerank score is below the confidence threshold.

    With the two-stage retrieval (cosine + cross-encoder rerank), the top_score
    passed here is the cross-encoder logit — a better proxy for true relevance
    than raw cosine similarity. When it falls below SIM_THRESHOLD, refuse the
    query without calling the LLM.
    """
    return top_score < settings.SIM_THRESHOLD