from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['*']

# Local development runs over http://127.0.0.1, so do not inherit production
# HTTPS and secure-cookie settings from base.py.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
