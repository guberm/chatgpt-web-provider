from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .backends import Backend, build_backend
from .config import Settings
from .models import ChatCompletionRequest, ChatMessage, ResponsesRequest
from .security import redact_secret


def _require_auth(settings: Settings):
    async def dep(authorization: Optional[str] = Header(default=None), x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> str:
        candidates: list[str] = []
        if x_api_key and x_api_key.strip() and not x_api_key.strip().startswith("{{"):
            candidates.append(x_api_key.strip())
        if authorization and authorization.lower().startswith("bearer "):
            candidates.append(authorization.split(" ", 1)[1].strip())

        if not candidates:
            raise HTTPException(status_code=401, detail="missing bearer token")
        for token in candidates:
            if token in settings.api_keys:
                return token
        raise HTTPException(status_code=403, detail="invalid bearer token")
    return dep


def _truthy_header(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


async def _run_with_queue(settings: Settings, queue_sem: asyncio.Semaphore, operation):
    try:
        async with asyncio.timeout(settings.queue_timeout_seconds):
            async with queue_sem:
                return await operation()
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="request timed out while waiting for provider queue") from exc



async def _chat_completion_stream(response_id: str, created: int, model: str, text: str, usage: dict):
    first = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
    }
    final = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": usage,
    }
    yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def create_app(settings: Settings | None = None, backend: Backend | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate_for_runtime()
    backend = backend or build_backend(settings)
    auth = _require_auth(settings)
    queue_sem = asyncio.Semaphore(settings.max_concurrent_requests)

    app = FastAPI(
        title="chatgpt-web-provider",
        version="0.1.0",
        description="OpenAI-compatible API facade for a browser-backed ChatGPT.com worker.",
    )
    app.state.settings = settings
    app.state.backend = backend

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": {"message": redact_secret(str(exc)), "type": exc.__class__.__name__}})

    @app.get("/health")
    async def health():
        data = await backend.health()
        return {"ok": bool(data.get("ok")), "backend": settings.backend, "model": settings.model_id, **data}

    @app.get("/v1/models")
    async def models(_token: str = Depends(auth)):
        return {
            "object": "list",
            "data": [
                {"id": settings.model_id, "object": "model", "created": 0, "owned_by": "chatgpt-web-provider"}
            ],
        }

    @app.get("/v1/provider/status")
    async def provider_status(_token: str = Depends(auth)):
        health_data = await backend.health()
        waiters = max(0, settings.max_concurrent_requests - getattr(queue_sem, "_value", settings.max_concurrent_requests))
        return {
            "backend": settings.backend,
            "model": settings.model_id,
            "health": health_data,
            "queue": {
                "max_concurrent_requests": settings.max_concurrent_requests,
                "queue_timeout_seconds": settings.queue_timeout_seconds,
                "in_flight_estimate": waiters,
            },
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest, x_new_session: Optional[str] = Header(default=None, alias="X-New-Session"), _token: str = Depends(auth)):
        started = int(time.time())
        new_session = req.new_session or _truthy_header(x_new_session)
        result = await _run_with_queue(
            settings,
            queue_sem,
            lambda: backend.complete(req.messages, model=req.model or settings.model_id, new_session=new_session),
        )
        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        usage = {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        }
        if req.stream:
            return StreamingResponse(
                _chat_completion_stream(response_id, started, result.model, result.text, usage),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return {
            "id": response_id,
            "object": "chat.completion",
            "created": started,
            "model": result.model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": result.text}, "finish_reason": "stop"}
            ],
            "usage": usage,
        }

    @app.post("/v1/responses")
    async def responses(req: ResponsesRequest, x_new_session: Optional[str] = Header(default=None, alias="X-New-Session"), _token: str = Depends(auth)):
        if req.stream:
            raise HTTPException(status_code=501, detail="streaming is not implemented yet")
        messages = _responses_input_to_messages(req.input)
        started = int(time.time())
        new_session = req.new_session or _truthy_header(x_new_session)
        result = await _run_with_queue(
            settings,
            queue_sem,
            lambda: backend.complete(messages, model=req.model or settings.model_id, new_session=new_session),
        )
        response_id = f"resp_{uuid.uuid4().hex}"
        return {
            "id": response_id,
            "object": "response",
            "created_at": started,
            "status": "completed",
            "model": result.model,
            "output": [
                {
                    "id": f"msg_{uuid.uuid4().hex}",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": result.text}],
                }
            ],
            "output_text": result.text,
            "usage": {
                "input_tokens": result.prompt_tokens,
                "output_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
            },
        }

    return app


def _responses_input_to_messages(value: str | list | dict) -> list[ChatMessage]:
    if isinstance(value, str):
        return [ChatMessage(role="user", content=value)]
    if isinstance(value, list):
        messages: list[ChatMessage] = []
        for item in value:
            if isinstance(item, dict) and "role" in item:
                content = item.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
                messages.append(ChatMessage(role=str(item.get("role", "user")), content=content))
        return messages or [ChatMessage(role="user", content=str(value))]
    return [ChatMessage(role="user", content=str(value))]


def main() -> None:
    settings = Settings.from_env()
    settings.validate_for_runtime()
    uvicorn.run("chatgpt_web_provider.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
