from __future__ import annotations

import re

_BEARER_RE = re.compile(r"Bearer\s+[^\s,;]+", re.IGNORECASE)
_SK_RE = re.compile(r"sk_live[A-Za-z0-9_\-]{12,}")
_ASSIGNMENT_RE = re.compile(r"\b(token|api[_-]?key|secret|password)=([^\s&]+)", re.IGNORECASE)


def redact_secret(text: str) -> str:
    """Redact common token shapes before logging or returning diagnostics."""
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", str(text))
    redacted = _SK_RE.sub("[REDACTED]", redacted)
    redacted = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
    return redacted
