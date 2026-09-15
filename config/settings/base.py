from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / '.env')

_INSECURE_SECRET_KEY = 'django-insecure-dev-only-do-not-use-in-prod'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', _INSECURE_SECRET_KEY)
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'

# In dev, accept any host. In prod, read a comma-separated list from the env so
# DEBUG=False doesn't fall back to an empty list that rejects every request.
ALLOWED_HOSTS = (
    ['*'] if DEBUG
    else [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]
)

# Fail loudly rather than silently serving prod traffic with the insecure
# development secret key.
if not DEBUG and SECRET_KEY == _INSECURE_SECRET_KEY:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set to a strong, unique value when DJANGO_DEBUG=False.'
    )

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.knowledge',
    'apps.rag',
    'apps.chatbot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    raise ImproperlyConfigured(
        'DATABASE_URL must be set. PostgreSQL is required; SQLite is not supported.'
    )

DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'chat_page'
LOGOUT_REDIRECT_URL = 'login'

# Employee self-registration is limited to one company email domain.
COMPANY_EMAIL_DOMAIN = os.getenv('COMPANY_EMAIL_DOMAIN', 'stemzglobal.com')

# Session cookie — long-lived so per-browser chat history persists without login.
# Each browser still gets a unique session_key, so User A can never see User B's chats.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365           # 1 year
SESSION_SAVE_EVERY_REQUEST = True                  # bump expiry on every visit
SESSION_EXPIRE_AT_BROWSER_CLOSE = False            # persist across browser restarts
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True                     # JS cannot read the cookie

# RAG / LLM config
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Speed-first model strategy.
CLAUDE_MODEL_FAST = os.getenv('CLAUDE_MODEL_FAST', 'claude-haiku-4-5-20251001')
CLAUDE_MODEL_DEFAULT = os.getenv('CLAUDE_MODEL_DEFAULT', 'claude-haiku-4-5-20251001')
CLAUDE_MODEL_ESCALATION = os.getenv('CLAUDE_MODEL_ESCALATION', 'claude-haiku-4-5-20251001')
FAST_SCORE_THRESHOLD = float(os.getenv('FAST_SCORE_THRESHOLD', '0.7'))
ESCALATION_SCORE_THRESHOLD = float(os.getenv('ESCALATION_SCORE_THRESHOLD', '0.3'))
SPEED_FIRST_MODE = os.getenv('SPEED_FIRST_MODE', 'True') == 'True'
FORCE_FAST_MODEL = os.getenv('FORCE_FAST_MODEL', 'True') == 'True'

# Kept for backwards compatibility with any tooling that reads CLAUDE_MODEL.
CLAUDE_MODEL = CLAUDE_MODEL_DEFAULT

SIM_THRESHOLD = float(os.getenv('SIM_THRESHOLD', '0.05'))
TOP_K = int(os.getenv('TOP_K', '5'))

# Fast defaults: skip CPU-heavy reranker unless explicitly enabled.
ENABLE_RERANK = os.getenv('ENABLE_RERANK', 'False') == 'True'
RETRIEVAL_CANDIDATE_POOL = int(os.getenv('RETRIEVAL_CANDIDATE_POOL', '10'))
MAX_CONTEXT_CHARS_PER_CHUNK = int(os.getenv('MAX_CONTEXT_CHARS_PER_CHUNK', '1600'))
MAX_DOCUMENT_CONTEXT_CHARS = int(os.getenv('MAX_DOCUMENT_CONTEXT_CHARS', '10000'))
MAX_HISTORY_MESSAGES = int(os.getenv('MAX_HISTORY_MESSAGES', '6'))
MAX_HISTORY_CHARS = int(os.getenv('MAX_HISTORY_CHARS', '500'))
MAX_LLM_TOKENS = int(os.getenv('MAX_LLM_TOKENS', '420'))
LLM_TIMEOUT_S = int(os.getenv('LLM_TIMEOUT_S', '8'))

KNOWLEDGE_DIR = BASE_DIR / 'knowledge'
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Admin dashboard (HTTP basic auth on /dashboard/)
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change-me')
if not DEBUG and ADMIN_PASSWORD in ('', 'change-me'):
    raise ImproperlyConfigured(
        'ADMIN_PASSWORD must be set to a non-default value when DJANGO_DEBUG=False.'
    )

# Email (Ask HR escalation) — Gmail SMTP with a Workspace app password.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_FROM', EMAIL_HOST_USER)
EMAIL_TO_HR = os.getenv('EMAIL_TO_HR', EMAIL_HOST_USER)  # where Ask HR requests land
ASK_HR_RECIPIENTS = [
    addr.strip() for addr in os.getenv('ASK_HR_RECIPIENTS', 'gandharvkartik@gmail.com').split(',')
    if addr.strip()
]

# Whisper (voice-to-text)
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'small')           # tiny | base | small | medium | large-v3
WHISPER_COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'int8')  # int8 (fast CPU) | float16 (GPU)
WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')           # cpu | cuda
WHISPER_MAX_AUDIO_MB = int(os.getenv('WHISPER_MAX_AUDIO_MB', '25'))  # reject uploads over this size

# Production hardening — only applied when DEBUG=False so local dev over http
# keeps working. Cookies go secure, HSTS is enabled, and MIME sniffing is off.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
