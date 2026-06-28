from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass(slots=True)
class Settings:
    api_keys: list[str] = field(default_factory=list)
    backend: str = "mock"
    model_id: str = "chatgpt-5.5-high-web"
    host: str = "127.0.0.1"
    port: int = 8791
    public_base_url: str = "http://127.0.0.1:8791"
    profile_dir: str = str(Path.home() / ".local/share/chatgpt-web-provider/chrome-profile")
    headless: bool = True
    request_timeout_seconds: int = 300
    max_concurrent_requests: int = 1
    queue_timeout_seconds: int = 600

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_keys=_csv(os.getenv("CHATGPT_WEB_API_KEYS")),
            backend=os.getenv("CHATGPT_WEB_BACKEND", "mock").strip().lower() or "mock",
            model_id=os.getenv("CHATGPT_WEB_MODEL", "chatgpt-5.5-high-web"),
            host=os.getenv("CHATGPT_WEB_HOST", "127.0.0.1"),
            port=int(os.getenv("CHATGPT_WEB_PORT", "8791")),
            public_base_url=os.getenv("CHATGPT_WEB_PUBLIC_BASE_URL", "http://127.0.0.1:8791"),
            profile_dir=os.getenv("CHATGPT_WEB_PROFILE_DIR", str(Path.home() / ".local/share/chatgpt-web-provider/chrome-profile")),
            headless=os.getenv("CHATGPT_WEB_HEADLESS", "true").lower() in {"1", "true", "yes", "on"},
            request_timeout_seconds=int(os.getenv("CHATGPT_WEB_REQUEST_TIMEOUT_SECONDS", "300")),
            max_concurrent_requests=int(os.getenv("CHATGPT_WEB_MAX_CONCURRENT_REQUESTS", "1")),
            queue_timeout_seconds=int(os.getenv("CHATGPT_WEB_QUEUE_TIMEOUT_SECONDS", "600")),
        )

    def validate_for_runtime(self) -> None:
        if not self.api_keys:
            raise ValueError("CHATGPT_WEB_API_KEYS must contain at least one API key")
        if self.backend not in {"mock", "browser"}:
            raise ValueError("CHATGPT_WEB_BACKEND must be 'mock' or 'browser'")
        if self.max_concurrent_requests < 1:
            raise ValueError("CHATGPT_WEB_MAX_CONCURRENT_REQUESTS must be >= 1")
        if self.queue_timeout_seconds < 1:
            raise ValueError("CHATGPT_WEB_QUEUE_TIMEOUT_SECONDS must be >= 1")
