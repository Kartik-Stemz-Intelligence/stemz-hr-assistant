"""Generate a PDF report covering chatbot speed improvements and
confidential-data escalation to HR.

Run:
  c:/Users/h4/Downloads/stemz-hr-assistant-main/.venv/Scripts/python.exe scripts/make_speed_confidential_report.py

Output:
  reports/speed-confidential-escalation-report.pdf
"""
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUT_DIR.mkdir(exist_ok=True)
OUT_PATH = OUT_DIR / "speed-confidential-escalation-report.pdf"

HTML = f"""
<html>
<head>
<style>
  body {{
    font-family: sans-serif;
    color: #1f2933;
    font-size: 10.5pt;
    line-height: 1.45;
  }}
  h1 {{
    color: #0b5394;
    font-size: 21pt;
    margin-bottom: 2px;
  }}
  h2 {{
    color: #0b5394;
    font-size: 14pt;
    margin-top: 18px;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 3px;
  }}
  h3 {{
    color: #334e68;
    font-size: 11.5pt;
    margin-top: 12px;
    margin-bottom: 3px;
  }}
  .subtitle {{
    color: #52606d;
    font-size: 11pt;
    margin-top: 0;
  }}
  .meta {{
    color: #7b8794;
    font-size: 9pt;
  }}
  code, pre {{
    font-family: monospace;
    background: #f0f4f8;
    color: #102a43;
  }}
  pre {{
    padding: 8px;
    border-left: 3px solid #0b5394;
    font-size: 9pt;
    white-space: pre-wrap;
  }}
  code {{
    padding: 1px 3px;
    font-size: 9.5pt;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 9.5pt;
  }}
  th, td {{
    border: 1px solid #cbd5e1;
    padding: 5px 7px;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background: #e3effb;
    color: #0b5394;
  }}
  .note {{
    background: #fff8e6;
    border-left: 3px solid #f0b429;
    padding: 7px 10px;
  }}
  .ok {{
    color: #0f7b3f;
    font-weight: bold;
  }}
  .warn {{
    color: #b45309;
    font-weight: bold;
  }}
  .no {{
    color: #b91c1c;
    font-weight: bold;
  }}
  ul {{
    margin-top: 4px;
  }}
  li {{
    margin-bottom: 2px;
  }}
</style>
</head>
<body>

<h1>Stemz HR Assistant</h1>
<p class="subtitle">Speed Improvements + Confidential Data to HR Escalation Report</p>
<p class="meta">Generated: {date.today().isoformat()} | Scope: chatbot backend flow, RAG guardrails, Ask-HR email path</p>

<h2>1. Executive Summary</h2>
<p>
This report documents two key tracks:
</p>
<ul>
  <li><b>Faster chat response behavior:</b> model routing, context trimming, timeout/caching, fallback answers, and user-visible streaming statuses.</li>
  <li><b>Safer handling of confidential policy content:</b> deterministic refusal before LLM generation and escalation support through the Ask-HR channel.</li>
</ul>
<p>
Net result: lower latency and better resilience, while preventing accidental disclosure of protected HR content.
</p>

<h2>2. What Was Improved for Speed</h2>
<table>
  <tr><th>Area</th><th>Implementation</th><th>Impact</th></tr>
  <tr>
    <td>Model selection</td>
    <td>Speed-first routing with confidence-based escalation</td>
    <td>Fast model serves most requests, slower/heavier model only when needed</td>
  </tr>
  <tr>
    <td>Context size</td>
    <td>Prior chat window is trimmed by count and character cap</td>
    <td>Lower prompt size, lower token cost, faster generation</td>
  </tr>
  <tr>
    <td>Timeout control</td>
    <td>LLM timeout enforced for streaming calls</td>
    <td>Prevents long-tail hangs</td>
  </tr>
  <tr>
    <td>Prompt caching hints</td>
    <td>Cache-control markers on stable system/prior blocks</td>
    <td>Improves repeated multi-turn performance</td>
  </tr>
  <tr>
    <td>Fallback answer</td>
    <td>Local short answer from top retrieved chunk when LLM fails</td>
    <td>User receives usable output instead of hard failure</td>
  </tr>
  <tr>
    <td>Perceived performance</td>
    <td>Early SSE status frames (searching/composing)</td>
    <td>Immediate UX feedback while backend is working</td>
  </tr>
</table>

<h3>2.1 Before vs After: Model Routing</h3>
<p><b>Before (single default model):</b></p>
<pre>selected_model = settings.CLAUDE_MODEL_DEFAULT</pre>

<p><b>After (speed-first + escalation):</b></p>
<pre>selected_model = _pick_model(top_score)

def _pick_model(top_score):
    if settings.FORCE_FAST_MODEL:
        return settings.CLAUDE_MODEL_FAST
    if settings.SPEED_FIRST_MODE:
        if top_score &lt; settings.ESCALATION_SCORE_THRESHOLD:
            return settings.CLAUDE_MODEL_ESCALATION
        return settings.CLAUDE_MODEL_FAST
    if top_score &lt; settings.ESCALATION_SCORE_THRESHOLD:
        return settings.CLAUDE_MODEL_ESCALATION
    if top_score &gt;= settings.FAST_SCORE_THRESHOLD:
        return settings.CLAUDE_MODEL_FAST
    return settings.CLAUDE_MODEL_DEFAULT</pre>

<h3>2.2 Before vs After: Prompt Window Trimming</h3>
<p><b>Before:</b></p>
<pre>prior_llm_messages = [{{'role': m.role, 'content': m.content}} for m in prior_messages]</pre>

<p><b>After:</b></p>
<pre>prior_llm_messages = _trim_prior_llm_messages(prior_llm_messages)

def _trim_prior_llm_messages(messages):
    max_messages = max(0, settings.MAX_HISTORY_MESSAGES)
    max_chars = max(1, settings.MAX_HISTORY_CHARS)
    ...</pre>

<h3>2.3 Before vs After: Timeout + Fallback</h3>
<p><b>Before:</b></p>
<pre>client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
for token in stream_answer(...):
    yield token</pre>

<p><b>After:</b></p>
<pre>client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    timeout=settings.LLM_TIMEOUT_S
)

try:
    for token in stream_answer(...):
        yield token
except Exception:
    fallback = _fallback_answer_from_retrieved(retrieved)
    yield fallback</pre>

<h2>3. Confidential Data Handling and HR Escalation</h2>
<table>
  <tr><th>Layer</th><th>What happens</th><th>Security effect</th></tr>
  <tr>
    <td>Ingestion</td>
    <td>Markdown frontmatter sets <code>confidential: true</code> and parser stamps chunk flag</td>
    <td>Confidentiality is machine-enforced per chunk</td>
  </tr>
  <tr>
    <td>Guardrail</td>
    <td>Retrieved set checked for confidential hit at relevant score</td>
    <td>Sensitive requests refused deterministically</td>
  </tr>
  <tr>
    <td>Generation gate</td>
    <td>Refusal path exits before LLM call</td>
    <td>Confidential text never enters model prompt</td>
  </tr>
  <tr>
    <td>Defense in depth</td>
    <td>Any remaining confidential chunks are filtered out pre-generation</td>
    <td>Secondary leakage prevention</td>
  </tr>
  <tr>
    <td>Ask-HR endpoint</td>
    <td>Escalation request persisted, then emailed to HR recipients</td>
    <td>No data loss if email delivery fails</td>
  </tr>
</table>

<h3>3.1 Before vs After: Confidential Guard</h3>
<p><b>Before:</b></p>
<pre># Retrieved chunks flowed directly to generation</pre>

<p><b>After:</b></p>
<pre>if confidential_hit(retrieved):
    yield _sse({{'type': 'token', 'text': CONFIDENTIAL_REFUSAL_MESSAGE}})
    Message.objects.create(..., content=CONFIDENTIAL_REFUSAL_MESSAGE, ...)
    yield _sse({{'type': 'done', 'confidence': 'refused', 'escalate': True}})
    return</pre>

<h3>3.2 Before vs After: Defense in Depth Filter</h3>
<p><b>Before:</b></p>
<pre># No explicit confidential filter before passing chunks to LLM</pre>

<p><b>After:</b></p>
<pre>retrieved = [r for r in retrieved if not is_confidential(r['chunk'])]</pre>

<h3>3.3 Before vs After: Ask-HR Reliability</h3>
<p><b>Before:</b></p>
<pre># Escalation path depended mainly on successful email delivery</pre>

<p><b>After:</b></p>
<pre>record = AskHRRequest.objects.create(...)

try:
    send_mail(...)
    record.email_status = 'sent'
except Exception as exc:
    record.email_status = 'failed'
    record.email_error = str(exc)[:2000]
    # Still persisted in DB for HR follow-up</pre>

<h2>4. End-to-End Flow</h2>
<table>
  <tr><th>Step</th><th>Condition</th><th>Outcome</th></tr>
  <tr><td>1. User asks question</td><td>Input is valid and within limits</td><td>Continue</td></tr>
  <tr><td>2. Retrieve</td><td>Top chunks returned with scores</td><td>Continue</td></tr>
  <tr><td>3. Confidential check</td><td>Any relevant confidential chunk present</td><td class="no">Refuse and suggest HR contact</td></tr>
  <tr><td>4. Refusal check</td><td>Low confidence / out of scope</td><td class="warn">Generic refusal and escalate option</td></tr>
  <tr><td>5. Generate</td><td>Non-confidential grounded context available</td><td class="ok">Stream answer with citation/source</td></tr>
  <tr><td>6. Ask-HR</td><td>User escalates</td><td class="ok">Persist request + email HR recipients</td></tr>
</table>

<h2>5. Validation Checklist</h2>
<ul>
  <li>Ask questions from non-confidential policies: answer should stream normally.</li>
  <li>Ask questions targeting confidential policies: confidential refusal should trigger.</li>
  <li>Force model timeout or failure: fallback answer should appear.</li>
  <li>Use Ask-HR with valid email: request should persist and send.</li>
  <li>Simulate mail failure: request should remain saved with failed status.</li>
</ul>

<div class="note">
  <b>Operational note:</b> For any newly confidential document, set frontmatter to
  <code>confidential: true</code> and re-run ingestion so chunk metadata is refreshed.
</div>

<h2>6. Key Code Locations</h2>
<ul>
  <li>Speed routing and stream flow: apps/chatbot/views.py</li>
  <li>Prompt build and timeout/caching: apps/rag/services/generate.py</li>
  <li>Confidential guardrail logic: apps/rag/services/guardrail.py</li>
  <li>Frontmatter-to-chunk confidential mapping: apps/knowledge/services/parser.py</li>
  <li>Ask-HR persistence model: apps/chatbot/models.py</li>
  <li>Speed/confidence/settings knobs: config/settings/base.py</li>
</ul>

</body>
</html>
"""


def build():
    writer = fitz.DocumentWriter(str(OUT_PATH))
    story = fitz.Story(html=HTML)

    page_rect = fitz.paper_rect("a4")
    content_rect = page_rect + (50, 50, -50, -50)

    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()

    writer.close()
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
