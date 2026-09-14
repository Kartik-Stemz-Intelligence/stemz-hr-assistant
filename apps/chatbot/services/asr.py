"""Automatic Speech Recognition — faster-whisper, self-hosted.

Design decisions:
- Model size 'small' (~460MB) — sweet spot for Indian English CPU inference.
- int8 quantization — ~2-4s latency for a 10s utterance on CPU.
- Domain initial_prompt biases decoding toward HR jargon (Keka, PF, HRA, etc).
- Post-transcription normalization dictionary fixes the most common jargon
  errors that Whisper mangles predictably.
- Model is loaded lazily on first call and cached for the process lifetime.
"""
import os
# Silence the huggingface_hub symlink warning on Windows. Symlinks are only a
# disk-space optimisation for de-duplicated files; not enabling them just means
# the cache stores copies, which is fine for a single-model install.
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
# Offline-by-default — Whisper weights are cached; stops HF hub check retries
# on startup when DNS/network is flaky. See embedder.py for full rationale.
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

import re
import threading

from django.conf import settings
from faster_whisper import WhisperModel


_MODEL = None
_LOCK = threading.Lock()

# ----- Domain glossary — fed to Whisper as initial_prompt ----------------
# Whisper conditions on this text and biases toward the tokens/phrases within it.
DOMAIN_PROMPT = (
    "This is an HR conversation at Stemz Global Healthcare. Common terms: "
    "Keka, PPO, LWP, LOP, CTC, EPF, EPFO, UAN, Form 16, ESIC, TDS, gratuity, "
    "casual leave, earned leave, sick leave, paid leave, notice period, "
    "probation, appraisal, WFH, work from home, OD, on-duty, biometric, "
    "attendance, PF, provident fund, HRA, LTA, DA, F&F, LWD, last working day, "
    "POSH, NDA, code of conduct, variable pay, KRA, OKR, HRBP, offer letter, "
    "joining bonus, relieving letter, experience letter, payslip, "
    "reimbursement, referral bonus, exit interview, background verification."
)

# ----- Post-transcription normalization ---------------------------------
# Whisper reliably mangles the same terms — patch them.
# Format: (regex_pattern_case_insensitive, replacement, word_boundary_required)
_NORMALIZATIONS = [
    (r'\bform sixteen\b', 'Form 16', True),
    (r'\bform 16\b', 'Form 16', True),
    (r'\b(?:l\s?w\s?p|loop)\b', 'LWP', True),
    (r'\bl\s?o\s?p\b', 'LOP', True),
    (r'\bc\s?t\s?c\b', 'CTC', True),
    (r'\bh\s?r\s?a\b', 'HRA', True),
    (r'\bl\s?t\s?a\b', 'LTA', True),
    (r'\bp\s?f\b', 'PF', True),
    (r'\bt\s?d\s?s\b', 'TDS', True),
    (r'\bu\s?a\s?n\b', 'UAN', True),
    (r'\be\s?p\s?f(?:\s?o)?\b', 'EPF', True),
    (r'\be\s?s\s?i\s?c\b', 'ESIC', True),
    (r'\bp\s?p\s?o\b', 'PPO', True),
    (r'\bp\s?p\s?u\b', 'PPO', True),
    (r'\bo\s?k\s?r\b', 'OKR', True),
    (r'\bk\s?r\s?a\b', 'KRA', True),
    (r'\bh\s?r\s?b\s?p\b', 'HRBP', True),
    (r'\b(?:cake\s?a|kekaa|kika|keeka)\b', 'Keka', True),
    (r'\bkeka\b', 'Keka', True),
    (r'\b(?:pausch|posh act|posch)\b', 'POSH', True),
    (r'\bposh\b', 'POSH', True),
    (r'\b(?:and\s?d\s?a|an\s?ndi|and\s?d\s?e\s?a)\b', 'NDA', True),
    (r'\bn\s?d\s?a\b', 'NDA', True),
    (r'\b(?:w\s?f\s?h|work[\s-]?from[\s-]?home)\b', 'WFH', True),
    (r'\b(?:o\s?d|on[\s-]?duty)\b', 'OD', True),
    (r'\b(?:l\s?w\s?d|last working day)\b', 'LWD', True),
    (r'\bf\s?and\s?f\b', 'F&F', True),
    (r'\bf\s?n\s?f\b', 'F&F', True),
]


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                model_size = getattr(settings, 'WHISPER_MODEL', 'small')
                compute_type = getattr(settings, 'WHISPER_COMPUTE_TYPE', 'int8')
                device = getattr(settings, 'WHISPER_DEVICE', 'cpu')
                _MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _MODEL


def normalize(text: str) -> str:
    """Apply domain-specific corrections to a raw transcript."""
    out = text
    for pattern, replacement, _wb in _NORMALIZATIONS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    # Collapse extra whitespace introduced by our substitutions
    out = re.sub(r'\s+', ' ', out).strip()
    return out


def transcribe(audio_path: str, language: str = 'en') -> dict:
    """Transcribe an audio file. Returns dict with 'text' (normalized),
    'raw' (pre-normalization), 'language', 'duration_s'.
    """
    model = _get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={'min_silence_duration_ms': 500},
        initial_prompt=DOMAIN_PROMPT,
        condition_on_previous_text=False,
    )
    raw = ''.join(segment.text for segment in segments).strip()
    normalized = normalize(raw)
    return {
        'text': normalized,
        'raw': raw,
        'language': info.language,
        'duration_s': round(info.duration, 2),
    }
