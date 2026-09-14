"""Generate a PDF report describing the confidential-document handling logic.

Run:  .venv\\Scripts\\python.exe scripts\\make_confidential_report.py
Output: reports/confidential-handling-report.pdf
"""
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUT_DIR.mkdir(exist_ok=True)
OUT_PATH = OUT_DIR / "confidential-handling-report.pdf"

HTML = f"""
<html>
<head>
<style>
  body {{ font-family: sans-serif; color: #1f2933; font-size: 10.5pt; line-height: 1.45; }}
  h1 {{ color: #0b5394; font-size: 21pt; margin-bottom: 2px; }}
  h2 {{ color: #0b5394; font-size: 14pt; margin-top: 18px;
        border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; }}
  h3 {{ color: #334e68; font-size: 11.5pt; margin-top: 12px; margin-bottom: 3px; }}
  .subtitle {{ color: #52606d; font-size: 11pt; margin-top: 0; }}
  .meta {{ color: #7b8794; font-size: 9pt; }}
  code, pre {{ font-family: monospace; background: #f0f4f8; color: #102a43; }}
  pre {{ padding: 8px; border-left: 3px solid #0b5394; font-size: 9pt;
         white-space: pre-wrap; }}
  code {{ padding: 1px 3px; font-size: 9.5pt; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 9.5pt; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 5px 7px; text-align: left;
            vertical-align: top; }}
  th {{ background: #e3effb; color: #0b5394; }}
  .note {{ background: #fff8e6; border-left: 3px solid #f0b429; padding: 7px 10px; }}
  .ok {{ color: #0f7b3f; font-weight: bold; }}
  .no {{ color: #b91c1c; font-weight: bold; }}
  ul {{ margin-top: 4px; }}
  li {{ margin-bottom: 2px; }}
</style>
</head>
<body>

<h1>Stemz HR Assistant</h1>
<p class="subtitle">Confidential-Document Handling &mdash; Change &amp; Logic Report</p>
<p class="meta">Generated: {date.today().isoformat()} &nbsp;|&nbsp; Scope: RAG guardrail for confidential HR policies</p>

<h2>1. Objective</h2>
<p>
Some HR policy documents (for example the <b>Executive Compensation Framework</b>
and the <b>IT Team Declaration</b>) contain information that must never be
disclosed to employees through the chatbot. The goal of this change is to make the
assistant <b>detect</b> such documents and <b>refuse</b> to answer from them &mdash;
redirecting the user to HR &mdash; without ever sending the confidential content to
the language model.
</p>

<h2>2. Summary of Changes</h2>
<table>
  <tr><th>Layer</th><th>File</th><th>What was added</th></tr>
  <tr>
    <td>Ingestion</td>
    <td>apps/knowledge/services/parser.py</td>
    <td>Reads <code>confidential: true</code> from each document's YAML
        frontmatter and stamps a boolean <code>confidential</code> flag onto
        every chunk of that document.</td>
  </tr>
  <tr>
    <td>Guardrail</td>
    <td>apps/rag/services/guardrail.py</td>
    <td>New <code>is_confidential(chunk)</code> helper and a dedicated
        <code>CONFIDENTIAL_REFUSAL_MESSAGE</code> constant.</td>
  </tr>
  <tr>
    <td>Request flow</td>
    <td>apps/chatbot/views.py</td>
    <td>A confidential guard that short-circuits the response before any LLM
        call, plus a defense-in-depth filter that strips confidential chunks
        from the context.</td>
  </tr>
  <tr>
    <td>Content</td>
    <td>knowledge/*.md</td>
    <td>Sensitive documents marked with <code>confidential: true</code> in
        their frontmatter.</td>
  </tr>
</table>

<h2>3. How It Works</h2>

<h3>3.1 Flagging at ingest time</h3>
<p>
When a markdown policy is parsed, its frontmatter is read and the confidential
flag is normalised to a real boolean and attached to <b>every</b> chunk, so the
retrieval pipeline never loses track of it:
</p>
<pre>base['confidential'] = str(metadata.get('confidential', '')).strip().lower() \\
    in ('true', 'yes', '1')</pre>
<p>
Accepting <code>true</code>, <code>yes</code>, or <code>1</code> makes the flag
tolerant of how the frontmatter is authored.
</p>

<h3>3.2 The guardrail helper</h3>
<pre>def is_confidential(chunk):
    return bool(chunk and chunk.get('confidential'))</pre>
<p>
A single source of truth for "is this chunk from a confidential document?",
used in two places in the request flow.
</p>

<h3>3.3 Confidential guard in the request flow</h3>
<p>
After retrieval, the <b>top-ranked</b> chunk is inspected. If it belongs to a
confidential document, the assistant streams a fixed refusal message, logs the
exchange, and returns &mdash; <b>before</b> any call to the LLM:
</p>
<pre>if is_confidential(top_chunk):
    yield _sse({{'type': 'token', 'text': CONFIDENTIAL_REFUSAL_MESSAGE}})
    Message.objects.create(..., content=CONFIDENTIAL_REFUSAL_MESSAGE, ...)
    yield _sse({{'type': 'done', 'confidence': 'refused'}})
    return</pre>

<h3>3.4 Defense in depth</h3>
<p>
Even after the top-chunk guard passes, any lower-ranked confidential chunk that
slipped into the results is removed before the context is handed to the model:
</p>
<pre>retrieved = [r for r in retrieved if not is_confidential(r['chunk'])]</pre>

<h2>4. Decision Flow</h2>
<table>
  <tr><th>Step</th><th>Condition</th><th>Outcome</th></tr>
  <tr><td>1. Retrieve</td><td>Top-k chunks fetched (cosine + reranker)</td><td>Continue</td></tr>
  <tr><td>2. Confidential guard</td><td>Top chunk <code>confidential = true</code></td><td class="no">Refuse &rarr; redirect to HR (no LLM)</td></tr>
  <tr><td>3. Confidence guard</td><td>Top rerank score &lt; <code>SIM_THRESHOLD</code></td><td class="no">Generic refusal (no LLM)</td></tr>
  <tr><td>4. Filter</td><td>Drop any remaining confidential chunks</td><td>Continue</td></tr>
  <tr><td>5. Generate</td><td>Grounded prompt to Claude</td><td class="ok">Answer with Source citation</td></tr>
</table>

<h2>5. The Two Refusal Messages</h2>
<table>
  <tr><th>Constant</th><th>When</th><th>Message</th></tr>
  <tr>
    <td><code>CONFIDENTIAL_REFUSAL_MESSAGE</code></td>
    <td>Top chunk is from a confidential document</td>
    <td>"This question relates to a confidential document that I'm not able to
        discuss. Please contact HR directly for assistance with this."</td>
  </tr>
  <tr>
    <td><code>REFUSAL_MESSAGE</code></td>
    <td>Top score below the similarity threshold (out of scope)</td>
    <td>"I don't have that information in the current policy documents.
        I'll connect you with HR."</td>
  </tr>
</table>

<h2>6. Why This Design</h2>
<ul>
  <li><b>No leak to the model.</b> Confidential content is blocked before the
      LLM call, so it can never appear in a prompt or a generated answer.</li>
  <li><b>Deterministic.</b> The refusal is a fixed string, not model output &mdash;
      it cannot be jailbroken or paraphrased into a disclosure.</li>
  <li><b>Data-driven.</b> Marking a document confidential is a one-line
      frontmatter change; no code edits required to protect a new document.</li>
  <li><b>Layered.</b> Top-chunk guard plus a context filter provides
      defense in depth.</li>
  <li><b>Auditable.</b> Every refusal is written to the Message log with the
      retrieved titles and top score.</li>
</ul>

<h2>7. How to Test</h2>
<h3>Should trigger the CONFIDENTIAL refusal</h3>
<ul>
  <li>What are the salary bands for the CEO and CFO?</li>
  <li>How is the executive bonus structure calculated?</li>
  <li>What is the equity grant and vesting schedule for executives?</li>
  <li>What severance and change-of-control terms do executives get?</li>
</ul>
<h3>Should still be answered (non-confidential confidentiality policies)</h3>
<ul>
  <li>What are my confidentiality obligations at Stemz? <span class="ok">(NDA)</span></li>
  <li>How long do post-employment confidentiality obligations last?</li>
  <li>How must I handle visa applicant data?</li>
</ul>
<div class="note">
  <b>Note:</b> To protect a new document, add <code>confidential: true</code> to its
  frontmatter and re-run <code>python manage.py ingest_docs</code>. The flag only
  takes effect after re-ingestion.
</div>

</body>
</html>
"""


def build():
    writer = fitz.DocumentWriter(str(OUT_PATH))
    story = fitz.Story(html=HTML)
    # A4 page with margins.
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
