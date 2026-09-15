import os
import threading

from django.apps import AppConfig


class RagConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rag'
    label = 'rag'

    def ready(self):
        # Only warm-load in the actual server worker.
        # - RUN_MAIN='true' is set by Django's autoreloader in the reloaded
        #   worker process (dev server); the parent process shouldn't preload.
        # - The 'runserver' / 'runserver_plus' / gunicorn cases are covered by
        #   the RUN_MAIN check + the DISABLE_MODEL_WARMUP escape hatch below.
        # - Skip when running management commands (migrate, ingest_docs, shell,
        #   tests, etc.) so those stay snappy.
        if os.environ.get('DISABLE_MODEL_WARMUP') == '1':
            return

        import sys
        argv = sys.argv
        # Only warm on runserver. `migrate`, `ingest_docs`, `shell`, `test`,
        # `collectstatic` etc. don't need the models and would slow to a crawl.
        is_runserver = any(cmd in argv for cmd in ('runserver', 'runserver_plus'))
        is_wsgi_worker = 'gunicorn' in argv[0] if argv else False

        if not (is_runserver or is_wsgi_worker):
            return

        # Django's autoreloader forks; only warm inside the reloaded worker,
        # not the parent watcher process.
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return

        # Background thread so `runserver` starts serving immediately.
        # The first request that lands during warm-up will just wait for the
        # existing load — no duplicate loads because both paths use the same
        # module-level singleton (_MODEL) with a lock.
        thread = threading.Thread(target=_warm_models, name='model-warmup', daemon=True)
        thread.start()


def _warm_models():
    """Force embedder + reranker weights to load into RAM.

    Loaded sequentially, not in parallel threads: transformers'/accelerate's
    meta-device model init is not thread-safe, and constructing both models
    concurrently corrupts one of them (`Cannot copy out of meta tensor`).
    """
    import time

    started = time.time()
    print('[warmup] Loading embedder + reranker…')

    timings = {}
    errors = {}

    def load_embedder():
        try:
            from apps.knowledge.services.embedder import embed
            t0 = time.time()
            embed('warmup')  # trivial call triggers weight load
            timings['embedder'] = time.time() - t0
        except Exception as exc:
            errors['embedder'] = exc

    def load_reranker():
        try:
            from apps.rag.services.reranker import rerank
            t0 = time.time()
            rerank('warmup', [{'chunk': {'text': 'warmup'}}], top_k=1)
            timings['reranker'] = time.time() - t0
        except Exception as exc:
            errors['reranker'] = exc

    load_embedder()
    load_reranker()

    total = time.time() - started
    emb_t = timings.get('embedder', 0)
    rrk_t = timings.get('reranker', 0)

    if errors:
        # Never crash the server; the first real query re-tries and surfaces the error.
        for name, exc in errors.items():
            print(f'[warmup] {name} failed (non-fatal): {exc}')
    else:
        print(
            f'[warmup] Ready in {total:.1f}s '
            f'(embedder {emb_t:.1f}s + reranker {rrk_t:.1f}s).'
        )
