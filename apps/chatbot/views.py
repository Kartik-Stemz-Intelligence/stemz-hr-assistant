import base64
import json
import os
import tempfile
from functools import wraps

from django.conf import settings
from django.core.mail import send_mail
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods

from apps.rag.services.retrieve import retrieve
from apps.rag.services.guardrail import should_refuse, REFUSAL_MESSAGE
from apps.rag.services.generate import stream_answer, stream_answer_from_document
from apps.chatbot.services.titler import generate_title
from apps.chatbot.services.asr import transcribe as asr_transcribe
from apps.chatbot.services.dashboard import load_documents
from apps.chatbot.services.document import (
    extract_text as extract_document_text,
    DocumentError, MAX_UPLOAD_BYTES, SUPPORTED_EXTS,
)

from .models import Conversation, Message, AskHRRequest


UPLOAD_SESSION_KEY = 'uploaded_context'  # session key that holds the current doc


def _basic_auth_required(view_func):
    """Simple HTTP Basic Auth gate — for the internal /dashboard/ only.
    Credentials in .env (ADMIN_USER, ADMIN_PASSWORD).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if header.startswith('Basic '):
            try:
                decoded = base64.b64decode(header[6:]).decode('utf-8')
                user, _, pwd = decoded.partition(':')
                if user == settings.ADMIN_USER and pwd == settings.ADMIN_PASSWORD:
                    return view_func(request, *args, **kwargs)
            except (ValueError, UnicodeDecodeError):
                pass
        resp = HttpResponse('Authentication required', status=401)
        resp['WWW-Authenticate'] = 'Basic realm="Stemz HR Dashboard"'
        return resp
    return wrapper


def _sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


def _confidence_tier(score):
    """Map rerank score (sigmoid, 0-1) to a UI confidence badge."""
    if score >= 0.7:
        return 'high'
    if score >= 0.3:
        return 'medium'
    return 'low'


def _message_confidence(m):
    """Confidence tier for a stored assistant message. Returns 'refused' for
    guardrail refusals (so historical reloads match the live-stream badge)
    otherwise falls back to the score-based tier.
    """
    if m.role != 'assistant':
        return None
    if m.content == REFUSAL_MESSAGE:
        return 'refused'
    if m.top_score is None:
        return None
    return _confidence_tier(m.top_score)


def _short_model_name(model_id):
    """Turn a Claude model id into a friendly label for status messages."""
    m = (model_id or '').lower()
    if 'haiku' in m:  return 'Haiku'
    if 'sonnet' in m: return 'Sonnet'
    if 'opus' in m:   return 'Opus'
    return 'Claude'


def _pick_model(top_score):
    """Three-tier model picker driven by retrieval confidence:
      - high  (>= 0.7): Haiku 4.5 — retrieval already nailed it, LLM just formats
      - low   (<  0.3): Opus 4.8  — weak evidence, needs deeper reasoning
      - other:          Sonnet 5  — balanced default
    """
    if top_score < settings.ESCALATION_SCORE_THRESHOLD:
        return settings.CLAUDE_MODEL_ESCALATION
    if top_score >= settings.FAST_SCORE_THRESHOLD:
        return settings.CLAUDE_MODEL_FAST
    return settings.CLAUDE_MODEL_DEFAULT


def _source_info(chunk):
    """Package chunk metadata for the UI — powers the citation line and the
    click-to-verify excerpt. Every field is optional; the UI hides what's
    missing so pre-frontmatter chunks still render sensibly.
    """
    if not chunk:
        return None
    return {
        'doc_title': chunk.get('doc_title') or chunk.get('document', 'Untitled'),
        'section': chunk.get('title', ''),
        'category': chunk.get('category', ''),
        'version': chunk.get('version', ''),
        'effective_date': chunk.get('effective_date', ''),
        'approved_by': chunk.get('approved_by', ''),
        'signed_on': chunk.get('signed_on', ''),
        'status': chunk.get('status', ''),
        'excerpt': chunk.get('text', ''),
    }


def _conversation_summary(conv, snippet_len=80):
    last_msg = conv.messages.order_by('-created_at').first()
    snippet = ''
    if last_msg:
        snippet = last_msg.content[:snippet_len].strip().replace('\n', ' ')
        if len(last_msg.content) > snippet_len:
            snippet += '…'
    return {
        'id': conv.pk,
        'title': conv.display_title,
        'has_title': bool(conv.title),
        'created_at': conv.created_at.isoformat(),
        'updated_at': conv.updated_at.isoformat(),
        'snippet': snippet,
        'message_count': conv.messages.count(),
    }


def _ensure_session(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _owned_conversations(request):
    return Conversation.objects.filter(
        session_key=_ensure_session(request),
        is_archived=False,
    )


# ---------------------------------------------------------------- Chat page

def chat_page(request):
    _ensure_session(request)
    return render(request, 'chatbot/chat.html')


# ---------------------------------------------------------------- Dashboard

@_basic_auth_required
def dashboard(request):
    """HR/Admin dashboard — lists every ingested policy with its metadata.
    Data is read fresh from chunks.json on each request (cheap; only ~200 rows).
    """
    data = load_documents()
    return render(request, 'chatbot/dashboard.html', data)


# ---------------------------------------------------------------- Conversations API

@csrf_exempt
@require_http_methods(['GET', 'POST'])
def conversations_list(request):
    if request.method == 'GET':
        convs = _owned_conversations(request).order_by('-updated_at')
        return JsonResponse({
            'conversations': [_conversation_summary(c) for c in convs],
        })

    # POST — create a new empty conversation
    conv = Conversation.objects.create(session_key=_ensure_session(request))
    return JsonResponse(_conversation_summary(conv), status=201)


@csrf_exempt
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def conversation_detail(request, pk):
    conv = _owned_conversations(request).filter(pk=pk).first()
    if not conv:
        return JsonResponse({'error': 'Conversation not found'}, status=404)

    if request.method == 'GET':
        messages = conv.messages.order_by('created_at')
        return JsonResponse({
            'id': conv.pk,
            'title': conv.display_title,
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat(),
            'messages': [
                {
                    'id': m.pk,
                    'role': m.role,
                    'content': m.content,
                    'citation': m.citation,
                    'top_score': m.top_score,
                    'confidence': _message_confidence(m),
                    'source': m.source or None,
                    'created_at': m.created_at.isoformat(),
                }
                for m in messages
            ],
        })

    if request.method == 'PATCH':
        try:
            body = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'title' in body:
            title = (body['title'] or '').strip()
            if not title:
                return JsonResponse({'error': 'Title cannot be empty'}, status=400)
            conv.title = title[:120]
        if 'is_archived' in body:
            conv.is_archived = bool(body['is_archived'])
        conv.save()
        return JsonResponse(_conversation_summary(conv))

    # DELETE
    conv.delete()
    return HttpResponse(status=204)


# ---------------------------------------------------------------- Chat stream

@csrf_exempt
@require_POST
def chat_stream(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    query = (body.get('message') or '').strip()
    if not query:
        return JsonResponse({'error': 'Empty message'}, status=400)

    session_key = _ensure_session(request)

    # Resolve conversation: use provided one (session-owned) or create new
    conversation_id = body.get('conversation_id')
    if conversation_id:
        conversation = Conversation.objects.filter(
            pk=conversation_id, session_key=session_key, is_archived=False,
        ).first()
        if not conversation:
            return JsonResponse({'error': 'Conversation not found'}, status=404)
    else:
        conversation = Conversation.objects.create(session_key=session_key)

    is_first_exchange = not conversation.messages.exists()
    prior_messages = list(conversation.messages.order_by('created_at')) if not is_first_exchange else []

    Message.objects.create(conversation=conversation, role='user', content=query)

    prior_llm_messages = [
        {'role': m.role, 'content': m.content}
        for m in prior_messages
    ]

    # Uploaded document mode — if the session holds a doc, bypass RAG entirely
    # and pass the doc directly to Claude. Different system prompt, different
    # source card in the UI.
    uploaded_doc = request.session.get(UPLOAD_SESSION_KEY)

    def event_stream():
        # Meta first — client uses conversation_id immediately for AskHR + sidebar wiring.
        yield _sse({
            'type': 'meta',
            'conversation_id': conversation.pk,
            'is_new_conversation': is_first_exchange,
        })

        # ------ Uploaded-document branch ------
        if uploaded_doc:
            yield from _stream_document_answer(
                query=query,
                uploaded=uploaded_doc,
                conversation=conversation,
                is_first_exchange=is_first_exchange,
                prior_llm_messages=prior_llm_messages,
            )
            return

        # ------ Standard RAG branch ------
        # Retrieval — takes 1-2s on CPU. Emit a status so the bubble isn't blank.
        yield _sse({'type': 'status', 'text': 'Searching policies…'})
        try:
            retrieved = retrieve(query)
        except FileNotFoundError as e:
            yield _sse({'type': 'error', 'text': str(e)})
            return
        except Exception as e:
            yield _sse({'type': 'error', 'text': f'Retrieval error: {e}'})
            return

        top = retrieved[0] if retrieved else None
        top_score = top['rerank_score'] if top else 0.0
        top_sim = top['score'] if top else 0.0
        top_chunk = top['chunk'] if top else None
        confidence = _confidence_tier(top_score) if top else 'low'
        selected_model = _pick_model(top_score)
        source = _source_info(top_chunk)
        retrieved_titles = [
            f"{r['chunk']['title']} (rerank={r.get('rerank_score', 0):.2f})"
            for r in retrieved
        ]

        yield _sse({
            'type': 'debug',
            'retrieved': retrieved_titles,
            'top_score': round(top_score, 3),
            'top_sim': round(top_sim, 3),
            'confidence': confidence,
            'model': selected_model,
        })
        # Status shown while we wait for Anthropic's TTFT (~1-2s).
        yield _sse({'type': 'status', 'text': f'Composing answer with {_short_model_name(selected_model)}…'})

        if should_refuse(top_score):
            yield _sse({'type': 'token', 'text': REFUSAL_MESSAGE})
            Message.objects.create(
                conversation=conversation,
                role='assistant',
                content=REFUSAL_MESSAGE,
                citation='',
                top_score=top_score,
                retrieved_titles=retrieved_titles,
            )
            # Save conversation to bump updated_at
            conversation.save()
            _maybe_generate_title(conversation, is_first_exchange, query, REFUSAL_MESSAGE)
            yield _sse({'type': 'done', 'confidence': 'refused'})
            if is_first_exchange and conversation.title:
                yield _sse({'type': 'title', 'title': conversation.title})
            return

        buffer = []
        try:
            for token in stream_answer(query, retrieved, prior_messages=prior_llm_messages, model=selected_model):
                buffer.append(token)
                yield _sse({'type': 'token', 'text': token})
        except Exception as exc:
            yield _sse({'type': 'error', 'text': f'Generation error: {exc}'})
            return

        full_answer = ''.join(buffer)
        citation = ''
        if source:
            citation = f"Source: {source['section']}, {source['doc_title']}"

        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=full_answer,
            citation=citation,
            top_score=top_score,
            retrieved_titles=retrieved_titles,
            source=source or {},
        )
        conversation.save()  # bump updated_at

        # Auto-title (fire-and-forget style but synchronous — Haiku is fast)
        _maybe_generate_title(conversation, is_first_exchange, query, full_answer)

        yield _sse({
            'type': 'done',
            'citation': citation,
            'confidence': confidence,
            'source': source,  # full metadata + excerpt for the click-to-verify UI
        })
        if is_first_exchange and conversation.title:
            yield _sse({'type': 'title', 'title': conversation.title, 'conversation_id': conversation.pk})

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def _stream_document_answer(query, uploaded, conversation, is_first_exchange, prior_llm_messages):
    """Yields SSE frames for the uploaded-document flow.

    Mirrors the shape of the RAG flow (meta already sent → status → debug →
    status → tokens → done) so the frontend uses the same rendering pipeline.
    The `source` payload here signals doc-mode to the UI, which swaps the
    citation card wording and hides the Ask HR button.
    """
    filename = uploaded.get('filename', 'uploaded document')
    doc_text = uploaded.get('text', '')
    chars = uploaded.get('chars', len(doc_text))

    yield _sse({'type': 'status', 'text': f'Reading {filename}…'})
    yield _sse({
        'type': 'debug',
        'retrieved': [f'Uploaded document: {filename} ({chars:,} chars)'],
        'top_score': 1.0,
        'top_sim': 1.0,
        'confidence': 'high',
        'model': settings.CLAUDE_MODEL_DEFAULT,
    })
    yield _sse({'type': 'status', 'text': f'Composing answer with {_short_model_name(settings.CLAUDE_MODEL_DEFAULT)}…'})

    buffer = []
    try:
        for token in stream_answer_from_document(
            query=query,
            document_text=doc_text,
            filename=filename,
            prior_messages=prior_llm_messages,
        ):
            buffer.append(token)
            yield _sse({'type': 'token', 'text': token})
    except Exception as exc:
        yield _sse({'type': 'error', 'text': f'Generation error: {exc}'})
        return

    full_answer = ''.join(buffer)
    citation = f'Answered from uploaded file: {filename}'
    source = {
        'doc_title': filename,
        'section': 'Uploaded document',
        'category': 'Personal upload',
        'version': '',
        'effective_date': '',
        'approved_by': '',
        'signed_on': '',
        'status': 'uploaded',                        # distinguishes doc-mode in UI
        'excerpt': doc_text[:1500],                  # preview only, not the whole file
        'is_uploaded': True,                         # explicit flag for the frontend
    }

    Message.objects.create(
        conversation=conversation,
        role='assistant',
        content=full_answer,
        citation=citation,
        top_score=1.0,
        retrieved_titles=[f'Uploaded: {filename}'],
        source=source,
    )
    conversation.save()
    _maybe_generate_title(conversation, is_first_exchange, query, full_answer)

    yield _sse({
        'type': 'done',
        'citation': citation,
        'confidence': 'high',
        'source': source,
    })
    if is_first_exchange and conversation.title:
        yield _sse({'type': 'title', 'title': conversation.title, 'conversation_id': conversation.pk})


def _maybe_generate_title(conversation, is_first_exchange, user_msg, bot_msg):
    """Generate a title if this is the first exchange and no title exists yet."""
    if not is_first_exchange or conversation.title:
        return
    try:
        title = generate_title(user_msg, bot_msg)
        if title:
            conversation.title = title
            conversation.save(update_fields=['title', 'updated_at'])
    except Exception:
        pass  # never break the response over a failed title


# ---------------------------------------------------------------- Transcribe

@csrf_exempt
@require_POST
def transcribe_audio(request):
    """Transcribe uploaded audio via faster-whisper. Returns {text, raw, language, duration_s}."""
    audio = request.FILES.get('audio')
    if not audio:
        return JsonResponse({'error': 'No audio file provided'}, status=400)

    max_bytes = settings.WHISPER_MAX_AUDIO_MB * 1024 * 1024
    if audio.size > max_bytes:
        return JsonResponse(
            {'error': f'Audio too large. Max size is {settings.WHISPER_MAX_AUDIO_MB} MB.'},
            status=413,
        )

    # Persist to a temp file so faster-whisper's demuxer can decode it.
    # Keep the original extension so the demuxer picks the right codec.
    ext = os.path.splitext(audio.name or '')[1] or '.webm'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        for chunk in audio.chunks():
            tmp.write(chunk)
        tmp.close()
        result = asr_transcribe(tmp.name, language='en')
        return JsonResponse(result)
    except Exception as exc:
        return JsonResponse({'error': f'Transcription failed: {exc}'}, status=500)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------- Upload

@csrf_exempt
@require_http_methods(['GET', 'POST', 'DELETE'])
def upload_document(request):
    """Manage the session's uploaded document.

    GET    → current state {filename, chars} or {filename: null}
    POST   → multipart file → extracts text → stores in session
    DELETE → clears the session's uploaded doc
    """
    _ensure_session(request)

    if request.method == 'GET':
        uploaded = request.session.get(UPLOAD_SESSION_KEY)
        if not uploaded:
            return JsonResponse({'filename': None})
        return JsonResponse({
            'filename': uploaded.get('filename'),
            'chars': uploaded.get('chars', 0),
        })

    if request.method == 'DELETE':
        request.session.pop(UPLOAD_SESSION_KEY, None)
        request.session.modified = True
        return JsonResponse({'ok': True})

    # POST — upload
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)
    if file.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {'error': f'File too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'},
            status=413,
        )

    try:
        text = extract_document_text(file.read(), file.name)
    except DocumentError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        # Unknown parser failure — log-ish message, don't leak internals
        return JsonResponse(
            {'error': f'Could not read {file.name}: {type(e).__name__}'},
            status=400,
        )

    request.session[UPLOAD_SESSION_KEY] = {
        'filename': file.name,
        'text': text,
        'chars': len(text),
    }
    request.session.modified = True

    return JsonResponse({
        'ok': True,
        'filename': file.name,
        'chars': len(text),
    })


# ---------------------------------------------------------------- Ask HR

def _format_ask_hr_email(record):
    """Plain-text email — reliable across mail clients, avoids spam filters."""
    convo_link = f"Conversation #{record.conversation_id}" if record.conversation_id else "(no conversation)"

    # Django stores datetimes as UTC when USE_TZ=True. localtime() converts to
    # settings.TIME_ZONE (Asia/Kolkata) so the recipient sees IST, not UTC.
    created_local = timezone.localtime(record.created_at)

    lines = [
        f"An employee has escalated a question from the HR AI assistant.",
        "",
        f"From:        {record.user_name} <{record.user_email}>",
        f"When:        {created_local.strftime('%a, %d %b %Y, %H:%M')} IST",
        f"Convo ref:   {convo_link}",
        "",
        "─" * 60,
        "USER'S QUESTION",
        "─" * 60,
        record.question or '(empty)',
        "",
    ]

    if record.bot_answer:
        lines += [
            "─" * 60,
            "WHAT THE BOT SAID",
            "─" * 60,
            record.bot_answer,
            "",
        ]

    if record.user_note:
        lines += [
            "─" * 60,
            "USER'S CONCERN",
            "─" * 60,
            record.user_note,
            "",
        ]

    if record.retrieved_titles:
        lines += [
            "─" * 60,
            "POLICY SECTIONS THE BOT USED",
            "─" * 60,
        ]
        lines += [f"  · {t}" for t in record.retrieved_titles]
        lines.append("")

    if record.transcript:
        lines += [
            "─" * 60,
            "FULL CONVERSATION TRANSCRIPT",
            "─" * 60,
        ]
        for turn in record.transcript:
            role = turn.get('role', 'user').upper()
            content = turn.get('content', '')
            lines.append(f"[{role}] {content}")
            lines.append("")

    lines += [
        "─" * 60,
        "Please reply directly to the user's email above.",
        "This message was generated by the Stemz HR AI assistant.",
    ]
    return '\n'.join(lines)


@csrf_exempt
@require_POST
def ask_hr(request):
    """Escalate the current chat context to HR by email. Also persists to DB
    so nothing is lost if delivery fails.
    """
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = (body.get('name') or '').strip()
    email = (body.get('email') or '').strip()
    note = (body.get('note') or '').strip()
    conversation_id = body.get('conversation_id')

    if not name or not email:
        return JsonResponse({'error': 'Name and email are required'}, status=400)

    # Look up the conversation (session-owned) — optional but preferred.
    conversation = None
    question = ''
    bot_answer = ''
    transcript = []
    retrieved_titles = []
    top_score = None

    if conversation_id:
        session_key = _ensure_session(request)
        conversation = Conversation.objects.filter(
            pk=conversation_id, session_key=session_key,
        ).first()

    if conversation:
        msgs = list(conversation.messages.order_by('created_at'))
        transcript = [{'role': m.role, 'content': m.content} for m in msgs]
        # Question = last user message; bot_answer = last assistant reply
        for m in reversed(msgs):
            if not question and m.role == 'user':
                question = m.content
            if not bot_answer and m.role == 'assistant':
                bot_answer = m.content
                retrieved_titles = m.retrieved_titles or []
                top_score = m.top_score
            if question and bot_answer:
                break

    # Allow the client to override question/answer if the modal captured them
    # directly (avoids a race with the DB when firing right after streaming).
    question = (body.get('question') or question).strip()
    bot_answer = (body.get('bot_answer') or bot_answer).strip()

    if not question:
        return JsonResponse({'error': 'No question to escalate'}, status=400)

    record = AskHRRequest.objects.create(
        conversation=conversation,
        user_name=name[:120],
        user_email=email,
        question=question,
        bot_answer=bot_answer,
        user_note=note,
        transcript=transcript,
        retrieved_titles=retrieved_titles,
        top_score=top_score,
    )

    subject = f"[HR Bot Escalation] {name}: {question[:60]}"
    message = _format_ask_hr_email(record)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_TO_HR],
            reply_to=[email] if email else None,
            fail_silently=False,
        )
        record.email_status = 'sent'
        record.save(update_fields=['email_status'])
    except TypeError:
        # Older Django send_mail doesn't accept reply_to — fall back to EmailMessage
        from django.core.mail import EmailMessage
        try:
            msg = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.EMAIL_TO_HR],
                reply_to=[email] if email else None,
            )
            msg.send(fail_silently=False)
            record.email_status = 'sent'
            record.save(update_fields=['email_status'])
        except Exception as exc:
            record.email_status = 'failed'
            record.email_error = str(exc)[:2000]
            record.save(update_fields=['email_status', 'email_error'])
            return JsonResponse({
                'ok': False,
                'saved': True,
                'error': 'Saved but email failed. HR will still see it in the dashboard.',
            }, status=502)
    except Exception as exc:
        record.email_status = 'failed'
        record.email_error = str(exc)[:2000]
        record.save(update_fields=['email_status', 'email_error'])
        return JsonResponse({
            'ok': False,
            'saved': True,
            'error': 'Saved but email failed. HR will still see it in the dashboard.',
        }, status=502)

    return JsonResponse({
        'ok': True,
        'id': record.pk,
        'message': f"Sent to HR. They'll reply to {email}.",
    })
