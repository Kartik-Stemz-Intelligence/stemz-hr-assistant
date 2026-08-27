"""
Baseline eval bank — runs across the full ingested corpus.

Permanent regression baseline. Every change to embeddings, chunk strategy,
threshold, or retrieval must keep these tests green. Add every new confirmed
policy Q&A here when new documents are ingested.

Format:
- GROUNDED_QUESTIONS: (question, expected_document_substring)
  where expected_document_substring must appear in the top-3 retrieved chunks'
  `document` field.
- OUT_OF_SCOPE_QUESTIONS: questions with no relevant policy content anywhere
  in the corpus. Must trigger the sub-threshold refusal.
"""
import pytest

from apps.rag.services.retrieve import retrieve, clear_cache
from apps.rag.services.guardrail import should_refuse


# Each tuple: (question, expected_document_substring — matched against
# `document` field of retrieved chunks)
GROUNDED_QUESTIONS = [
    # Attendance Policy
    ('How many late arrivals are allowed per month?', 'Attendance'),
    ('How many WFH days can I take per month?', 'Attendance'),
    ('How is attendance tracked?', 'Attendance'),
    ('How many regularization requests per month?', 'Attendance'),
    ('What happens if I miss a swipe?', 'Attendance'),
    ('Can I raise an OD request for a past date?', 'Attendance'),

    # Attendance Policy — Office Timings (v1.1 addition)
    ('What are the standard office timings?', 'Attendance'),
    ('How many hours do I need to work per day?', 'Attendance'),
    ('What is the weekly work hour quota?', 'Attendance'),
    ('What is the latest time I can start work?', 'Attendance'),
    ('Can I come to office at 10 AM?', 'Attendance'),
    ('What is the daily minimum work hours?', 'Attendance'),
    ('Is 10:10 AM considered late arrival?', 'Attendance'),

    # Welcome Email
    ('What time should I reach the office on Day 1?', 'Welcome Email'),
    ('What documents should I bring on my first day?', 'Welcome Email'),
    ('What is the dress code on Day 1?', 'Welcome Email'),
    ('Where is the Stemz office located?', 'Offices'),

    # Variable Pay Policy
    ('Am I eligible for variable pay during notice period?', 'Variable Pay'),
    ('When is variable pay paid out?', 'Variable Pay'),
    ('How is variable pay calculated?', 'Variable Pay'),
    ('What is the OKR rating for exceptional talent?', 'Variable Pay'),

    # IT Team Declaration
    ('Can I use ChatGPT with company code?', 'IT Declaration'),
    ('Can I share my admin password with a teammate?', 'IT Declaration'),

    # NDA and Confidentiality (joining)
    ('What are my confidentiality obligations at Stemz?', 'Non-Disclosure'),
    ('Who owns the code I write while at Stemz?', 'Non-Disclosure'),

    # Undertaking-cum-Indemnity (exit)
    ('What confidentiality applies after I leave Stemz?', 'Indemnity'),
    ('Can I contact Stemz employees for hiring after I leave?', 'Indemnity'),

    # Anti-Bribery
    ('What are the anti-bribery obligations at Stemz?', 'Anti-Bribery'),

    # Data Protection
    ('Can I forward company data to my personal email?', 'Data Protection'),

    # CCTV
    ('Is the office monitored by CCTV?', 'CCTV'),
    ('Can I request access to CCTV footage?', 'CCTV'),

    # Conflict of Interest
    ('Do I need to declare a relative working at Stemz?', 'Conflict of Interest'),

    # Photography / Acceptable Use
    ('Can I take photos inside the office?', 'Acceptable Use'),

    # Change of Circumstances
    ('What if my nationality changes?', 'Change of Circumstances'),
    ('What if I get a new passport?', 'Change of Circumstances'),

    # Laptop Usage
    ('What happens if I damage my company laptop?', 'Laptop'),
    ('Can I install personal software on my company laptop?', 'Laptop'),

    # Exit Clearance
    ('What items do I hand over on my last day?', 'Exit Clearance'),
    ('When is my email account deleted after I leave?', 'Exit Clearance'),

    # Employee Declaration (exit)
    ('What am I signing at exit related to my NDA?', 'Employee Declaration'),

    # Asset Loss Self-Declaration (accept either Laptop or Self-Declaration doc)
    ('What happens if I lose my laptop before leaving?', 'Laptop'),
    ('Will the cost of a damaged asset be deducted from my final settlement?', 'Self-Declaration'),

    # Gratuity Nomination
    ('Who can I nominate for gratuity?', 'Gratuity'),

    # Code of Conduct Ack
    ('What am I acknowledging about the Code of Conduct?', 'Code of Conduct'),

    # Stemz Company Overview
    ('What does Stemz do?', 'Company Overview'),
    ('What is the Stemz mission?', 'Company Overview'),
    ('What is the Stemz vision?', 'Company Overview'),
    ('What are the business verticals of Stemz?', 'Company Overview'),
    ('What certifications does Stemz hold?', 'Company Overview'),

    # Stemz Offices
    ('Where is Stemz headquartered?', 'Offices'),
    ('Where is the Stemz office in Dubai?', 'Offices'),
    ('What is the Gurugram corporate address?', 'Offices'),

    # Stemz History and Milestones
    ('When was Stemz founded?', 'History'),
    ('Who did Stemz partner with in Saudi Arabia?', 'History'),
    ('When did Stemz get ISO 27001 certification?', 'History'),
    ('What awards has Stemz won?', 'History'),
]

OUT_OF_SCOPE_QUESTIONS = [
    'What is the capital of Brazil?',
    'What stock should I invest in?',
    'What is the weather today?',
    'Can you recommend a good movie?',
    'What is the recipe for biryani?',
    'Tell me a joke about dogs',
]


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield


@pytest.mark.parametrize('question,expected_document', GROUNDED_QUESTIONS)
def test_grounded_retrieval(question, expected_document):
    results = retrieve(question, k=3)
    assert results, 'Retrieval should return at least one chunk'
    docs = [r['chunk']['document'] for r in results]
    assert any(expected_document in d for d in docs), (
        f"Expected a chunk from '{expected_document}' in top-3 for '{question}'; "
        f"got documents: {docs}"
    )
    assert not should_refuse(results[0]['rerank_score']), (
        f"'{question}' should NOT trigger refusal "
        f"(top_score={results[0]['rerank_score']:.3f})"
    )


@pytest.mark.parametrize('question', OUT_OF_SCOPE_QUESTIONS)
def test_refusal_for_out_of_scope(question):
    results = retrieve(question, k=3)
    assert should_refuse(results[0]['rerank_score']), (
        f"'{question}' SHOULD trigger refusal "
        f"(top_score={results[0]['rerank_score']:.3f} exceeded threshold)"
    )
