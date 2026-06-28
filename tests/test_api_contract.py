import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from chatgpt_web_provider.app import create_app
from chatgpt_web_provider.backends import Backend
from chatgpt_web_provider.config import Settings
from chatgpt_web_provider.models import ChatMessage, CompletionResult


@pytest.fixture()
def client():
    app = create_app(Settings(api_keys=["test-token"], backend="mock", public_base_url="https://codex.guber.dev"))
    return TestClient(app)


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["backend"] == "mock"


def test_models_requires_bearer_token(client):
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_models_returns_openai_compatible_shape(client):
    r = client.get("/v1/models", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    assert data["data"][0]["id"] == "chatgpt-5.5-high-web"


def test_models_accepts_x_api_key_header(client):
    r = client.get("/v1/models", headers={"X-API-Key": "test-token"})
    assert r.status_code == 200
    assert r.json()["data"][0]["id"] == "chatgpt-5.5-high-web"


def test_provider_status_requires_auth_and_reports_queue(client):
    assert client.get("/v1/provider/status").status_code == 401
    r = client.get("/v1/provider/status", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["backend"] == "mock"
    assert data["model"] == "chatgpt-5.5-high-web"
    assert data["queue"]["max_concurrent_requests"] == 1


def test_chat_completions_non_stream(client):
    payload = {
        "model": "chatgpt-5.5-high-web",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say pong"},
        ],
    }
    r = client.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "chatgpt-5.5-high-web"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "Say pong" in data["choices"][0]["message"]["content"]
    assert data["choices"][0]["finish_reason"] == "stop"


def test_responses_endpoint_returns_openai_responses_like_shape(client):
    r = client.post(
        "/v1/responses",
        json={"model": "chatgpt-5.5-high-web", "input": "hello"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "response"
    assert data["model"] == "chatgpt-5.5-high-web"
    assert data["output"][0]["content"][0]["type"] == "output_text"
    assert "hello" in data["output_text"]


def test_streaming_is_explicitly_not_implemented_yet(client):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "chatgpt-5.5-high-web", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 501


class SlowBackend(Backend):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.active = 0
        self.max_active = 0

    async def complete(self, messages: list[ChatMessage], model: str | None = None) -> CompletionResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.05)
        self.active -= 1
        return CompletionResult(text="ok", model=model or self.settings.model_id)


def test_requests_are_queued_by_default():
    async def run():
        settings = Settings(api_keys=["test-token"], backend="mock", max_concurrent_requests=1)
        backend = SlowBackend(settings)
        app = create_app(settings, backend=backend)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {"model": "chatgpt-5.5-high-web", "messages": [{"role": "user", "content": "hi"}]}
            responses = await asyncio.gather(
                ac.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer test-token"}),
                ac.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer test-token"}),
            )
        assert [r.status_code for r in responses] == [200, 200]
        assert backend.max_active == 1

    asyncio.run(run())
