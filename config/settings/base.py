from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-only-do-not-use-in-prod')
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*'] if DEBUG else []

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
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

# Session cookie — long-lived so per-browser chat history persists without login.
# Each browser still gets a unique session_key, so User A can never see User B's chats.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365           # 1 year
SESSION_SAVE_EVERY_REQUEST = True                  # bump expiry on every visit
SESSION_EXPIRE_AT_BROWSER_CLOSE = False            # persist across browser restarts
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True                     # JS cannot read the cookie

# RAG / LLM config
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Three-tier model strategy — the LLM's job scales with retrieval quality:
# - score >= FAST_SCORE_THRESHOLD (0.7) → Haiku 4.5. High-confidence hits where
#   retrieval already did the work; the LLM just formats. Fastest TTFT.
# - between the two → Sonnet 5. Solid grounded synthesis for the middle.
# - score <  ESCALATION_SCORE_THRESHOLD (0.3) → Opus 4.8. Low-confidence cases
#   where the LLM has to stitch weaker evidence — the deeper reasoning earns its cost.
CLAUDE_MODEL_FAST = os.getenv('CLAUDE_MODEL_FAST', 'claude-haiku-4-5-20251001')
CLAUDE_MODEL_DEFAULT = os.getenv('CLAUDE_MODEL_DEFAULT', 'claude-sonnet-5')
CLAUDE_MODEL_ESCALATION = os.getenv('CLAUDE_MODEL_ESCALATION', 'claude-opus-4-8')
FAST_SCORE_THRESHOLD = float(os.getenv('FAST_SCORE_THRESHOLD', '0.7'))
ESCALATION_SCORE_THRESHOLD = float(os.getenv('ESCALATION_SCORE_THRESHOLD', '0.3'))

# Kept for backwards compatibility with any tooling that reads CLAUDE_MODEL.
CLAUDE_MODEL = CLAUDE_MODEL_DEFAULT

SIM_THRESHOLD = float(os.getenv('SIM_THRESHOLD', '0.05'))
TOP_K = int(os.getenv('TOP_K', '8'))

KNOWLEDGE_DIR = BASE_DIR / 'knowledge'
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Admin dashboard (HTTP basic auth on /dashboard/)
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change-me')

# Email (Ask HR escalation) — Gmail SMTP with a Workspace app password.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_FROM', EMAIL_HOST_USER)
EMAIL_TO_HR = os.getenv('EMAIL_TO_HR', EMAIL_HOST_USER)  # where Ask HR requests land

# Whisper (voice-to-text)
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'small')           # tiny | base | small | medium | large-v3
WHISPER_COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'int8')  # int8 (fast CPU) | float16 (GPU)
WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')           # cpu | cuda
WHISPER_MAX_AUDIO_MB = int(os.getenv('WHISPER_MAX_AUDIO_MB', '25'))  # reject uploads over this size
