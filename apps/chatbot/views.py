import base64
import json
import os
import secrets
import tempfile
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.rag.services.retrieve import retrieve
from apps.rag.services.guardrail import (
    should_refuse, REFUSAL_MESSAGE,
    is_confidential, confidential_hit, CONFIDENTIAL_REFUSAL_MESSAGE,
)
from apps.rag.services.generate import stream_answer, stream_answer_from_document
from apps.chatbot.services.asr import transcribe as asr_transcribe
from apps.chatbot.services.dashboard import load_documents
from apps.chatbot.services.titler import generate_title
from apps.chatbot.services.document import (
    extract_text as extract_document_text,
    DocumentError, MAX_UPLOAD_BYTES, SUPPORTED_EXTS,
)

from .forms import (
    EmployeeLoginForm,
    EmployeeRegistrationRequestForm,
    EmployeeRegistrationVerifyForm,
    EmployeeRegistrationPasswordForm,
    ForgotPasswordEmailForm,
    ForgotPasswordVerifyForm,
    ForgotPasswordResetForm,
)
from .models import Conversation, Message, AskHRRequest


UPLOAD_SESSION_KEY = 'uploaded_context'  # session key that holds the current doc

MAX_QUERY_CHARS = 5000   # reject oversized chat messages before they hit the LLM
REGISTRATION_SESSION_KEY = 'employee_registration_pending'
REGISTRATION_CODE_TTL_MINUTES = 10
REGISTRATION_MAX_VERIFY_ATTEMPTS = 5
FORGOT_PASSWORD_SESSION_KEY = 'forgot_password_pending'
FORGOT_PASSWORD_CODE_TTL_MINUTES = 10
FORGOT_PASSWORD_MAX_VERIFY_ATTEMPTS = 5


def _rate_limit(bucket, limit, window_s):
    """Per-session sliding-window guard against endpoint abuse (spam, DoS).
    Falls back to client IP when there's no session yet. Backed by the default
    local-memory cache — good enough for a single-process deployment.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ident = _ensure_session(request) or request.META.get('REMOTE_ADDR', 'anon')
            key = f'rl:{bucket}:{ident}'
            if cache.get(key, 0) >= limit:
                return JsonResponse(
                    {'error': 'Too many requests. Please slow down and try again shortly.'},
                    status=429,
                )
            cache.add(key, 0, timeout=window_s)
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window_s)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


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


def _json_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Please log in with your employee account.'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def _safe_next_url(request, default='chat_page'):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def _registration_session(request):
    return request.session.get(REGISTRATION_SESSION_KEY)


def _save_registration_session(request, payload):
    request.session[REGISTRATION_SESSION_KEY] = payload
    request.session.modified = True


def _clear_registration_session(request):
    if REGISTRATION_SESSION_KEY in request.session:
        request.session.pop(REGISTRATION_SESSION_KEY, None)
        request.session.modified = True


def _send_registration_code_email(email, code):
    subject = 'Stemz HR Assistant verification code'
    message = (
        'Use the following verification code to create your Stemz HR Assistant account.\n\n'
        f'Code: {code}\n\n'
        f'This code expires in {REGISTRATION_CODE_TTL_MINUTES} minutes.\n\n'
        'If you did not request this, you can ignore this email.'
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def _start_registration(request, full_name, email):
    code = f'{secrets.randbelow(1000000):06d}'
    expires_at = timezone.now() + timedelta(minutes=REGISTRATION_CODE_TTL_MINUTES)
    payload = {
        'full_name': full_name,
        'email': email,
        'code_hash': make_password(code),
        'expires_at': expires_at.isoformat(),
        'attempts': 0,
        'verified': False,
    }
    _save_registration_session(request, payload)
    _send_registration_code_email(email, code)


def _is_registration_expired(payload):
    expires_at = payload.get('expires_at')
    if not expires_at:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(expires_at)
    except ValueError:
        return True


def _create_user_from_pending(payload, password):
    email = (payload.get('email') or '').strip().lower()
    full_name = (payload.get('full_name') or '').strip()
    user = User(username=email, email=email)
    if full_name:
        name_parts = full_name.split(None, 1)
        user.first_name = name_parts[0]
        if len(name_parts) > 1:
            user.last_name = name_parts[1]
    user.set_password(password)
    user.save()
    return user


def _forgot_password_session(request):
    return request.session.get(FORGOT_PASSWORD_SESSION_KEY)


def _save_forgot_password_session(request, payload):
    request.session[FORGOT_PASSWORD_SESSION_KEY] = payload
    request.session.modified = True


def _clear_forgot_password_session(request):
    if FORGOT_PASSWORD_SESSION_KEY in request.session:
        request.session.pop(FORGOT_PASSWORD_SESSION_KEY, None)
        request.session.modified = True


def _send_forgot_password_code_email(email, code):
    subject = 'Stemz HR Assistant password reset code'
    message = (
        'Use the following verification code to reset your Stemz HR Assistant password.\n\n'
        f'Code: {code}\n\n'
        f'This code expires in {FORGOT_PASSWORD_CODE_TTL_MINUTES} minutes.\n\n'
        'If you did not request this, you can ignore this email.'
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def _start_forgot_password(request, email):
    code = f'{secrets.randbelow(1000000):06d}'
    expires_at = timezone.now() + timedelta(minutes=FORGOT_PASSWORD_CODE_TTL_MINUTES)
    payload = {
        'email': email,
        'code_hash': make_password(code),
        'expires_at': expires_at.isoformat(),
        'attempts': 0,
        'verified': False,
    }
    _save_forgot_password_session(request, payload)
    _send_forgot_password_code_email(email, code)


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
    if m.content in (REFUSAL_MESSAGE, CONFIDENTIAL_REFUSAL_MESSAGE):
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
    """Speed-first model picker with optional low-confidence escalation."""
    if settings.FORCE_FAST_MODEL:
        return settings.CLAUDE_MODEL_FAST
    if settings.SPEED_FIRST_MODE:
        if top_score < settings.ESCALATION_SCORE_THRESHOLD:
            return settings.CLAUDE_MODEL_ESCALATION
        return settings.CLAUDE_MODEL_FAST
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
    source_file = chunk.get('source_file', '')
    page_number = chunk.get('page_number', 1)
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
        'source_file': source_file,
        'source_type': chunk.get('source_type', ''),
        'page_number': page_number,
        'citation_link': f'/view-document/?file={quote(source_file)}&page={page_number}' if source_file else '',
    }


def _trim_prior_llm_messages(messages):
    """Keep only a small recent context window for faster generation."""
    if not messages:
        return []
    max_messages = max(0, settings.MAX_HISTORY_MESSAGES)
    max_chars = max(1, settings.MAX_HISTORY_CHARS)
    window = messages[-max_messages:] if max_messages else []
    trimmed = []
    for msg in window:
        content = (msg.get('content') or '').strip()
        if not content:
            continue
        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + '…'
        trimmed.append({'role': msg.get('role', 'user'), 'content': content})
    return trimmed


def _fallback_answer_from_retrieved(retrieved):
    """Return a short local fallback answer when the LLM is slow/unavailable."""
    if not retrieved:
        return REFUSAL_MESSAGE
    top_chunk = (retrieved[0] or {}).get('chunk') or {}
    section = top_chunk.get('title') or 'policy section'
    doc = top_chunk.get('doc_title') or top_chunk.get('document') or 'policy document'
    text = (top_chunk.get('text') or '').strip().replace('\n', ' ')
    if len(text) > 360:
        text = text[:360].rstrip() + '…'
    if not text:
        return f"I found guidance in {section} ({doc}), but the full response is delayed. Please try again or contact HR for immediate help."
    return f"Quick policy note from {section} ({doc}): {text}"


def _fallback_answer_from_document(filename, document_text):
    """Return a short local fallback answer for uploaded-document mode."""
    excerpt = (document_text or '').strip().replace('\n', ' ')
    if len(excerpt) > 360:
        excerpt = excerpt[:360].rstrip() + '…'
    if not excerpt:
        return f"I could not generate a full answer from {filename} in time. Please try again."
    return f"Quick note from {filename}: {excerpt}"


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
    if request.user.is_authenticated:
        return Conversation.objects.filter(
            user_id=str(request.user.pk),
            is_archived=False,
        )
    return Conversation.objects.filter(
        session_key=_ensure_session(request),
        is_archived=False,
    )


def _conversation_owner_kwargs(request):
    kwargs = {'session_key': _ensure_session(request)}
    if request.user.is_authenticated:
        kwargs['user_id'] = str(request.user.pk)
    return kwargs


# ---------------------------------------------------------------- Chat page

def login_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    form = EmployeeLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['email'],
            password=form.cleaned_data['password'],
        )
        if user is None:
            form.add_error(None, 'Invalid email or password.')
        else:
            login(request, user)
            return redirect(_safe_next_url(request))

    return render(request, 'chatbot/login.html', {'form': form, 'next': request.GET.get('next', '')})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    form = EmployeeRegistrationRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        full_name = (form.cleaned_data.get('full_name') or '').strip()
        email = form.cleaned_data['email']
        _start_registration(request, full_name, email)
        return redirect('register_verify')

    return render(request, 'chatbot/register.html', {'form': form, 'next': request.GET.get('next', '')})


def register_verify_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    pending = _registration_session(request)
    if not pending:
        return redirect('register')

    if _is_registration_expired(pending):
        _clear_registration_session(request)
        return render(request, 'chatbot/register_verify.html', {
            'form': EmployeeRegistrationVerifyForm(),
            'email': '',
            'expired': True,
        })

    form = EmployeeRegistrationVerifyForm(request.POST or None)
    if request.method == 'POST':
        action = (request.POST.get('action') or 'verify').strip().lower()
        if action == 'resend':
            _start_registration(request, pending.get('full_name', ''), pending.get('email', ''))
            return render(request, 'chatbot/register_verify.html', {
                'form': EmployeeRegistrationVerifyForm(),
                'email': pending.get('email', ''),
                'resent': True,
                'expired': False,
            })

        if form.is_valid():
            if pending.get('attempts', 0) >= REGISTRATION_MAX_VERIFY_ATTEMPTS:
                form.add_error('code', 'Too many invalid attempts. Request a new code.')
            elif check_password(form.cleaned_data['code'], pending.get('code_hash', '')):
                pending['verified'] = True
                pending['code_hash'] = ''
                _save_registration_session(request, pending)
                return redirect('register_password')
            else:
                pending['attempts'] = int(pending.get('attempts', 0)) + 1
                _save_registration_session(request, pending)
                remaining = max(0, REGISTRATION_MAX_VERIFY_ATTEMPTS - pending['attempts'])
                form.add_error('code', f'Invalid code. {remaining} attempt(s) left.')

    return render(request, 'chatbot/register_verify.html', {
        'form': form,
        'email': pending.get('email', ''),
        'expired': False,
    })


def register_password_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    pending = _registration_session(request)
    if not pending or not pending.get('verified'):
        return redirect('register')

    email = (pending.get('email') or '').strip().lower()
    if not email:
        _clear_registration_session(request)
        return redirect('register')

    if User.objects.filter(username__iexact=email).exists():
        _clear_registration_session(request)
        return redirect('login')

    form = EmployeeRegistrationPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = _create_user_from_pending(pending, form.cleaned_data['password1'])
        _clear_registration_session(request)
        login(request, user)
        return redirect(_safe_next_url(request))

    return render(request, 'chatbot/register_password.html', {
        'form': form,
        'email': email,
    })


def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    form = ForgotPasswordEmailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        _start_forgot_password(request, form.cleaned_data['email'])
        return redirect('forgot_password_verify')

    return render(request, 'chatbot/forgot_password.html', {'form': form})


def forgot_password_verify_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    pending = _forgot_password_session(request)
    if not pending:
        return redirect('forgot_password')

    if _is_registration_expired(pending):
        _clear_forgot_password_session(request)
        return render(request, 'chatbot/forgot_password_verify.html', {
            'form': ForgotPasswordVerifyForm(),
            'email': '',
            'expired': True,
        })

    form = ForgotPasswordVerifyForm(request.POST or None)
    if request.method == 'POST':
        action = (request.POST.get('action') or 'verify').strip().lower()
        if action == 'resend':
            _start_forgot_password(request, pending.get('email', ''))
            return render(request, 'chatbot/forgot_password_verify.html', {
                'form': ForgotPasswordVerifyForm(),
                'email': pending.get('email', ''),
                'resent': True,
                'expired': False,
            })

        if form.is_valid():
            if pending.get('attempts', 0) >= FORGOT_PASSWORD_MAX_VERIFY_ATTEMPTS:
                form.add_error('code', 'Too many invalid attempts. Request a new code.')
            elif check_password(form.cleaned_data['code'], pending.get('code_hash', '')):
                pending['verified'] = True
                pending['code_hash'] = ''
                _save_forgot_password_session(request, pending)
                return redirect('forgot_password_reset')
            else:
                pending['attempts'] = int(pending.get('attempts', 0)) + 1
                _save_forgot_password_session(request, pending)
                remaining = max(0, FORGOT_PASSWORD_MAX_VERIFY_ATTEMPTS - pending['attempts'])
                form.add_error('code', f'Invalid code. {remaining} attempt(s) left.')

    return render(request, 'chatbot/forgot_password_verify.html', {
        'form': form,
        'email': pending.get('email', ''),
        'expired': False,
    })


def forgot_password_reset_view(request):
    if request.user.is_authenticated:
        return redirect('chat_page')

    pending = _forgot_password_session(request)
    if not pending or not pending.get('verified'):
        return redirect('forgot_password')

    email = (pending.get('email') or '').strip().lower()
    if not email:
        _clear_forgot_password_session(request)
        return redirect('forgot_password')

    form = ForgotPasswordResetForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = User.objects.get(username__iexact=email)
        except User.DoesNotExist:
            _clear_forgot_password_session(request)
            return redirect('forgot_password')

        user.set_password(form.cleaned_data['password1'])
        user.save()
        _clear_forgot_password_session(request)
        return render(request, 'chatbot/forgot_password_success.html')

    return render(request, 'chatbot/forgot_password_reset.html', {
        'form': form,
        'email': email,
    })


@login_required(login_url='login')
@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
@ensure_csrf_cookie
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

@_json_login_required
@require_http_methods(['GET', 'POST'])
def conversations_list(request):
    if request.method == 'GET':
        convs = _owned_conversations(request).order_by('-updated_at')
        return JsonResponse({
            'conversations': [_conversation_summary(c) for c in convs],
        })

    # POST — create a new empty conversation
    conv = Conversation.objects.create(**_conversation_owner_kwargs(request))
    return JsonResponse(_conversation_summary(conv), status=201)


@_json_login_required
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

@_json_login_required
@require_POST
@_rate_limit('chat', limit=30, window_s=60)
def chat_stream(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    query = (body.get('message') or '').strip()
    if not query:
        return JsonResponse({'error': 'Empty message'}, status=400)
    if len(query) > MAX_QUERY_CHARS:
        return JsonResponse(
            {'error': f'Message too long. Maximum is {MAX_QUERY_CHARS} characters.'},
            status=400,
        )

    session_key = _ensure_session(request)

    # Resolve conversation: use provided one (session-owned) or create new
    conversation_id = body.get('conversation_id')
    if conversation_id:
        conversation = Conversation.objects.filter(
            pk=conversation_id,
            is_archived=False,
            **({'user_id': str(request.user.pk)} if request.user.is_authenticated else {'session_key': session_key}),
        ).first()
        if not conversation:
            return JsonResponse({'error': 'Conversation not found'}, status=404)
    else:
        conversation = Conversation.objects.create(**_conversation_owner_kwargs(request))

    is_first_exchange = not conversation.messages.exists()
    prior_messages = list(conversation.messages.order_by('created_at')) if not is_first_exchange else []

    Message.objects.create(conversation=conversation, role='user', content=query)

    prior_llm_messages = [
        {'role': m.role, 'content': m.content}
        for m in prior_messages
    ]
    prior_llm_messages = _trim_prior_llm_messages(prior_llm_messages)

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
        # Confidential-document guard: if any relevant retrieved chunk belongs
        # to a document flagged `confidential: true`, never answer — redirect to
        # HR. No LLM call, and confidential content never reaches the model.
        # Checking the whole reranked set (not just the top hit) keeps this
        # strict: a confidential document surfacing at all triggers a refusal.
        if confidential_hit(retrieved):
            yield _sse({'type': 'token', 'text': CONFIDENTIAL_REFUSAL_MESSAGE})
            Message.objects.create(
                conversation=conversation,
                role='assistant',
                content=CONFIDENTIAL_REFUSAL_MESSAGE,
                citation='',
                top_score=top_score,
                retrieved_titles=retrieved_titles,
            )
            conversation.save()
            _maybe_generate_title(conversation, is_first_exchange, query, CONFIDENTIAL_REFUSAL_MESSAGE)
            yield _sse({'type': 'done', 'confidence': 'refused', 'escalate': True})
            if is_first_exchange and conversation.title:
                yield _sse({'type': 'title', 'title': conversation.title})
            return

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
            yield _sse({'type': 'done', 'confidence': 'refused', 'escalate': True})
            if is_first_exchange and conversation.title:
                yield _sse({'type': 'title', 'title': conversation.title})
            return

        # Defense in depth: never pass confidential-doc chunks to the LLM, even
        # if a lower-ranked one slipped into the results.
        retrieved = [r for r in retrieved if not is_confidential(r['chunk'])]

        buffer = []
        try:
            for token in stream_answer(query, retrieved, prior_messages=prior_llm_messages, model=selected_model):
                buffer.append(token)
                yield _sse({'type': 'token', 'text': token})
        except Exception:
            fallback = _fallback_answer_from_retrieved(retrieved)
            yield _sse({'type': 'token', 'text': fallback})
            buffer = [fallback]

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
    except Exception:
        fallback = _fallback_answer_from_document(filename, doc_text)
        yield _sse({'type': 'token', 'text': fallback})
        buffer = [fallback]

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
    """Assign an intent-based title (like ChatGPT) on the first exchange."""
    if not is_first_exchange or conversation.title:
        return
    title = generate_title(user_msg or '', bot_msg or '')
    conversation.title = title or f'Conversation #{conversation.pk}'
    conversation.save(update_fields=['title', 'updated_at'])


# ---------------------------------------------------------------- Transcribe

@_json_login_required
@require_POST
@_rate_limit('transcribe', limit=20, window_s=60)
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
    except Exception:
        return JsonResponse({'error': 'Transcription failed. Please try again.'}, status=500)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------- Upload

@_json_login_required
@require_http_methods(['GET', 'POST', 'DELETE'])
@_rate_limit('upload', limit=20, window_s=60)
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


# ---------------------------------------------------------------- Document viewer

@xframe_options_sameorigin
def view_document(request):
    """Serve a viewer page for a citation link (?file=&page=).

    PDFs render inline (browser's built-in PDF viewer) jumped to the cited
    page, with a note banner calling out why that page opened. Non-PDF
    formats (e.g. .docx, which browsers can't render inline) fall back to a
    download card. Only files directly under KNOWLEDGE_DIR can be
    referenced — the filename is resolved strictly under that directory to
    block path traversal (e.g. '..\\..\\secrets.txt').

    Django's X_FRAME_OPTIONS default is DENY, which would block the raw PDF
    response from rendering inside our own same-origin iframe below — relax
    that to SAMEORIGIN just for this view.
    """
    filename = (request.GET.get('file') or '').strip()
    if not filename or '/' in filename or '\\' in filename or '..' in filename:
        return HttpResponse('Invalid file reference.', status=400)

    try:
        page = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    page = max(page, 1)

    docs_dir = settings.KNOWLEDGE_DIR.resolve()
    file_path = (docs_dir / filename).resolve()
    if docs_dir not in file_path.parents or not file_path.is_file():
        return HttpResponse('Document not found.', status=404)

    is_pdf = file_path.suffix.lower() == '.pdf'
    encoded_name = quote(filename)
    safe_name = escape(filename)
    download_url = f'/view-document/?file={encoded_name}&page={page}&download=1'

    if request.GET.get('download') == '1':
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)

    if is_pdf and request.GET.get('raw') == '1':
        # Served inline (no Content-Disposition: attachment) so the iframe's
        # built-in PDF viewer renders it instead of prompting a download.
        return FileResponse(open(file_path, 'rb'), content_type='application/pdf', filename=filename)

    if is_pdf:
        raw_url = f'/view-document/?file={encoded_name}&page={page}&raw=1'
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_name} — Page {page}</title>
<style>
html, body {{ height:100%; margin:0; font-family: system-ui, sans-serif; background:#f8f8f8; }}
.note {{ display:flex; align-items:center; gap:.5rem; background:#7a1b38; color:#fff; padding:.6rem 1rem; font-size:.9rem; font-weight:600; }}
.note a {{ color:#fff; text-decoration:underline; margin-left:auto; font-weight:500; font-size:.8rem; }}
iframe {{ width:100%; height:calc(100% - 2.6rem); border:none; }}
</style>
</head>
<body>
<div class="note">📍 The information related to your question is on page {page} of this document.<a href="{download_url}">Download</a></div>
<iframe src="{raw_url}#page={page}" title="{safe_name}"></iframe>
</body>
</html>"""
        return HttpResponse(html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_name} — Page {page}</title>
<style>
body {{ font-family: system-ui, sans-serif; background:#f8f8f8; padding:2rem; color:#1f2933; }}
.card {{ max-width: 520px; margin: 0 auto; background:#fff; border-radius:12px; padding:2rem; box-shadow:0 10px 30px rgba(15,23,42,.08); }}
a.button {{ display:inline-block; margin-top:1rem; background:#7a1b38; color:#fff; padding:.75rem 1.25rem; border-radius:10px; text-decoration:none; font-weight:600; }}
</style>
</head>
<body>
<div class="card">
<h1>{safe_name}</h1>
<p>📍 The information related to your question is on page {page} of this document.</p>
<p>Download the file below to view it at that page in Word or your local viewer.</p>
<a class="button" href="{download_url}">Download {safe_name}</a>
</div>
</body>
</html>"""
    return HttpResponse(html)


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


@_json_login_required
@require_POST
@_rate_limit('ask_hr', limit=5, window_s=60)
def ask_hr(request):
    """Escalate the current chat context to HR by email. Also persists to DB
    so nothing is lost if delivery fails.
    """
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if request.user.is_authenticated:
        name = (request.user.get_full_name() or request.user.get_username() or request.user.email or '').strip()
        email = (request.user.email or request.user.get_username() or '').strip()
    else:
        name = (body.get('name') or '').strip()
        email = (body.get('email') or '').strip()
    note = (body.get('note') or '').strip()
    conversation_id = body.get('conversation_id')

    if not name or not email:
        return JsonResponse({'error': 'Name and email are required'}, status=400)
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Please enter a valid email address'}, status=400)
    name = name[:120]

    # Look up the conversation (session-owned) — optional but preferred.
    conversation = None
    question = ''
    bot_answer = ''
    transcript = []
    retrieved_titles = []
    top_score = None

    if conversation_id:
        conversation = _owned_conversations(request).filter(pk=conversation_id).first()

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
    recipients = settings.ASK_HR_RECIPIENTS or [settings.EMAIL_TO_HR]

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
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
                to=recipients,
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
