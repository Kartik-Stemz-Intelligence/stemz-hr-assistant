from django.conf import settings


REFUSAL_MESSAGE = (
    "I don't have that information in the current policy documents. "
    "I'll connect you with HR."
)


def should_refuse(top_score):
    """Return True if the top rerank score is below the confidence threshold.

    With the two-stage retrieval (cosine + cross-encoder rerank), the top_score
    passed here is the cross-encoder logit — a better proxy for true relevance
    than raw cosine similarity. When it falls below SIM_THRESHOLD, refuse the
    query without calling the LLM.
    """
    return top_score < settings.SIM_THRESHOLD
