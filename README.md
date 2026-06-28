# chatgpt-web-provider

OpenAI-compatible API facade for a browser-controlled `chatgpt.com` worker.

This project is designed for personal/internal use: third-party tools call a normal
OpenAI-style HTTP API, while a local browser worker sends prompts to ChatGPT.com
behind the scenes.

> Status: MVP. The API/auth/service scaffolding works, including a real browser
> backend with a logged-in dedicated ChatGPT profile. The browser backend is
> inherently fragile because ChatGPT UI, Cloudflare checks, and selectors can
> change at any time. Do not expose this as a public paid API and review
> ChatGPT/OpenAI terms before use.

## Features

- `GET /health`
- `GET /v1/models`
- `GET /v1/provider/status`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- non-stream and SSE streaming support for `/v1/chat/completions`
- Bearer-token auth and `X-API-Key` support
- ignores unresolved Postman placeholders like `X-API-Key: $CHATGPT_WEB_API_KEY` when a valid bearer token is present
- `new_session` option for forcing a fresh ChatGPT conversation
- mock backend for tests/local smoke checks
- browser backend using Playwright persistent Chromium profile
- simple in-process request queue with provider status endpoint
- secret redaction helpers
- example systemd/Caddy/Postman assets

## API base URL

Local development:

```text
http://127.0.0.1:8791
```

Example hosted deployment used during development:

```text
https://codex.guber.dev
```

OpenAI-compatible base URL for clients that ask for one:

```text
https://codex.guber.dev/v1
```

## Authentication

Authenticated endpoints accept either header:

```http
Authorization: Bearer $CHATGPT_WEB_API_KEY
```

or:

```http
X-API-Key: $CHATGPT_WEB_API_KEY
```

If both are present, the server accepts any valid supplied token. This is useful
for Postman exports where `X-API-Key: $CHATGPT_WEB_API_KEY` may remain unresolved while
`Authorization: Bearer $CHATGPT_WEB_API_KEY` is valid.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env
python -m pytest
CHATGPT_WEB_API_KEYS=dev-token CHATGPT_WEB_BACKEND=mock chatgpt-web-provider
```

Smoke test with the mock backend:

```bash
curl -s http://127.0.0.1:8791/health

curl -s \
  -H "X-API-Key: $CHATGPT_WEB_API_KEY" \
  http://127.0.0.1:8791/v1/models

curl -s \
  -H "X-API-Key: $CHATGPT_WEB_API_KEY" \
  -H 'Content-Type: application/json' \
  http://127.0.0.1:8791/v1/chat/completions \
  -d '{"model":"chatgpt-5.5-high-web","messages":[{"role":"user","content":"Say pong"}]}'

curl -s \
  -H "X-API-Key: $CHATGPT_WEB_API_KEY" \
  http://127.0.0.1:8791/v1/provider/status
```

## Chat Completions API

Use this for normal chat clients:

```http
POST /v1/chat/completions
```

Non-streaming request:

```bash
curl --location 'https://codex.guber.dev/v1/chat/completions' \
  --header 'Content-Type: application/json' \
  --header 'User-Agent: PostmanRuntime/7.45.0' \
  --header "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  --data '{
    "model": "chatgpt-5.5-high-web",
    "messages": [
      {"role": "system", "content": "Reply concisely."},
      {"role": "user", "content": "Say exactly: pong"}
    ],
    "stream": false
  }'
```

Response shape:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1782610607,
  "model": "chatgpt-5.5-high-web",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "pong"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

Token usage is exact for the mock backend and currently best-effort/zero for the
browser backend unless token accounting is added separately.

### Streaming chat completions

Set `stream: true`:

```bash
curl --no-buffer --location 'https://codex.guber.dev/v1/chat/completions' \
  --header 'Content-Type: application/json' \
  --header 'User-Agent: PostmanRuntime/7.45.0' \
  --header "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  --data '{
    "model": "chatgpt-5.5-high-web",
    "messages": [{"role": "user", "content": "Say pong"}],
    "stream": true
  }'
```

The server returns OpenAI-style SSE chunks:

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk",..."finish_reason":"stop"...}

data: [DONE]
```

The current streaming shim waits for the browser completion and then emits the
answer as SSE. It is protocol-compatible, not true token-by-token browser
streaming yet.

## Responses API

The project also exposes an OpenAI Responses-like endpoint:

```http
POST /v1/responses
```

Example:

```bash
curl --location 'https://codex.guber.dev/v1/responses' \
  --header 'Content-Type: application/json' \
  --header 'User-Agent: PostmanRuntime/7.45.0' \
  --header "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  --data '{
    "model": "chatgpt-5.5-high-web",
    "input": "Say exactly: pong",
    "stream": false
  }'
```

Response includes `output_text`:

```json
{
  "id": "resp_...",
  "object": "response",
  "status": "completed",
  "model": "chatgpt-5.5-high-web",
  "output_text": "pong"
}
```

Streaming for `/v1/responses` is not implemented yet.

## Fresh ChatGPT sessions

By default, the browser backend continues whatever ChatGPT conversation the
browser worker is currently on.

To force a fresh ChatGPT conversation before the prompt, use either request body:

```json
{
  "model": "chatgpt-5.5-high-web",
  "messages": [{"role": "user", "content": "Start fresh"}],
  "new_session": true
}
```

or header:

```http
X-New-Session: true
```

Full curl with body flag:

```bash
curl --location 'https://codex.guber.dev/v1/chat/completions' \
  --header 'Content-Type: application/json' \
  --header 'User-Agent: PostmanRuntime/7.45.0' \
  --header "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  --data '{
    "model": "chatgpt-5.5-high-web",
    "messages": [{"role":"user","content":"Say exactly: fresh-session-pong"}],
    "stream": false,
    "new_session": true
  }'
```

Full curl with header:

```bash
curl --location 'https://codex.guber.dev/v1/chat/completions' \
  --header 'Content-Type: application/json' \
  --header 'User-Agent: PostmanRuntime/7.45.0' \
  --header "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  --header 'X-New-Session: true' \
  --data '{
    "model": "chatgpt-5.5-high-web",
    "messages": [{"role":"user","content":"Say exactly: fresh-session-pong"}],
    "stream": false
  }'
```

`new_session` is supported on both `/v1/chat/completions` and `/v1/responses`.

## Browser backend setup

The browser backend uses a dedicated persistent Chromium profile. Do not reuse
your normal browser profile.

Environment:

```bash
CHATGPT_WEB_BACKEND=browser
CHATGPT_WEB_PROFILE_DIR=$HOME/.local/share/chatgpt-web-provider/chrome-profile
CHATGPT_WEB_HEADLESS=false
```

Open a visible setup browser and log in:

```bash
cd ~/github/chatgpt-web-provider
. .venv/bin/activate
set -a
. ~/.config/chatgpt-web-provider/env
set +a
CHATGPT_WEB_HEADLESS=false chatgpt-web-provider-browser-setup
```

In the opened browser:

1. log in to `chatgpt.com`
2. pass any Cloudflare/browser checks
3. select the desired model, for example GPT-5.5 High
4. press Enter in the terminal running `chatgpt-web-provider-browser-setup` to close and save the profile

Then start the API service with the same profile.

### Headless vs headed mode

In practice, ChatGPT often blocks headless Chromium with a Cloudflare page like:

```text
Just a moment...
```

If `GET /health` reports title `Just a moment...`, run the browser backend in
headed mode on the desktop session instead of headless.

For a user-launched service on Linux/X11, the launcher can export:

```bash
export DISPLAY=:0
export XAUTHORITY=$HOME/.Xauthority
CHATGPT_WEB_HEADLESS=false
```

The development deployment uses this pattern because headless mode reached
Cloudflare but headed mode reached normal ChatGPT and produced real responses.

### Browser backend health

`GET /health` returns browser hints:

```json
{
  "ok": true,
  "backend": "browser",
  "model": "chatgpt-5.5-high-web",
  "title": "ChatGPT",
  "logged_in_hint": true
}
```

If `backend` is `mock`, you are not using the real browser worker. If responses
start with `[mock:...]`, you are still on the mock backend.

## Provider status and queue

`GET /v1/provider/status` shows backend health and queue settings:

```bash
curl -s \
  -H "Authorization: Bearer $CHATGPT_WEB_API_KEY" \
  -H 'User-Agent: PostmanRuntime/7.45.0' \
  https://codex.guber.dev/v1/provider/status
```

Example shape:

```json
{
  "backend": "browser",
  "model": "chatgpt-5.5-high-web",
  "health": {"ok": true, "backend": "browser", "title": "ChatGPT"},
  "queue": {
    "max_concurrent_requests": 1,
    "queue_timeout_seconds": 600,
    "in_flight_estimate": 0
  }
}
```

The browser backend is serialized by default. Keep concurrency at `1` unless you
add a real browser pool.

## Postman project

Import files from `postman/`:

1. `chatgpt-web-provider.postman_collection.json`
2. `chatgpt-web-provider.template.postman_environment.json`

Set environment variable:

```text
api_key = <api-key>
```

The collection includes:

- Health
- Models
- Provider Status
- Chat Completions - non-stream
- Chat Completions - new session
- Chat Completions - stream SSE
- Responses API

The collection sets:

```http
User-Agent: {{user_agent}}
```

with default:

```text
PostmanRuntime/7.45.0
```

This matters because Cloudflare may block generic clients such as Python's
default `urllib` user agent while allowing Postman/curl-style user agents.

## Environment

```bash
CHATGPT_WEB_API_KEYS=replace-with-a-long-random-token
CHATGPT_WEB_BACKEND=mock
CHATGPT_WEB_MODEL=chatgpt-5.5-high-web
CHATGPT_WEB_HOST=127.0.0.1
CHATGPT_WEB_PORT=8791
CHATGPT_WEB_PUBLIC_BASE_URL=https://codex.example.com
CHATGPT_WEB_PROFILE_DIR=/home/example/.local/share/chatgpt-web-provider/chrome-profile
CHATGPT_WEB_HEADLESS=true
CHATGPT_WEB_REQUEST_TIMEOUT_SECONDS=300
CHATGPT_WEB_MAX_CONCURRENT_REQUESTS=1
CHATGPT_WEB_QUEUE_TIMEOUT_SECONDS=600
```

See `.env.example`.

## Deployment notes from the development host

The development deployment used:

- app bound to `127.0.0.1:8791`
- Cloudflare Tunnel for `codex.guber.dev`
- API auth at the app layer
- dedicated ChatGPT profile under `~/.local/share/chatgpt-web-provider/chrome-profile`
- headed browser worker with `DISPLAY=:0` and `XAUTHORITY=$HOME/.Xauthority`
- cron/user launch scripts to keep app and tunnel running

These are operational notes, not requirements. You can run the same API behind
Caddy, nginx, Cloudflare Tunnel, Tailscale, or localhost only.

## Security model

Default intended deployment:

- bind app to `127.0.0.1`
- expose through your own reverse proxy only when protected by API keys and/or additional access controls
- use a dedicated ChatGPT browser profile
- keep the browser worker away from SSH keys, Hermes secrets, customer projects, and production secrets
- do not auto-confirm high-impact shell/MCP actions
- do not sell this as a public API
- review ChatGPT/OpenAI terms before use

This repo does not provide shell/MCP tools yet. Add those behind explicit allowlists,
argument schemas, approval gates, and audit logs.

## Troubleshooting

### Response starts with `[mock:...]`

You are on the mock backend. Set:

```bash
CHATGPT_WEB_BACKEND=browser
```

and restart the service.

### `/health` title is `Just a moment...`

The browser is stuck at Cloudflare. Use headed mode with a real desktop session:

```bash
CHATGPT_WEB_HEADLESS=false
export DISPLAY=:0
export XAUTHORITY=$HOME/.Xauthority
```

Then restart and log in/pass checks in the dedicated profile if needed.

### Public endpoint returns Cloudflare 502/530/1033

Separate origin from edge:

```bash
curl http://127.0.0.1:8791/health
pgrep -af cloudflared
```

If local health works but public fails, restart/check the Cloudflare Tunnel. If
local health fails, fix the app first.

### Auth returns 401/403

Use one of:

```http
Authorization: Bearer $CHATGPT_WEB_API_KEY
X-API-Key: $CHATGPT_WEB_API_KEY
```

If using Postman, make sure `api_key` is set in the active environment. If both
headers are present, a valid bearer token still works even if `X-API-Key` is an
unresolved `{{api_key}}` placeholder.

### Postman/curl works but Python urllib gets blocked

Set a non-default user agent, for example:

```http
User-Agent: PostmanRuntime/7.45.0
```

## Current limitations

- browser automation depends on ChatGPT UI selectors
- no true browser token-by-token streaming yet
- `/v1/responses` streaming is not implemented
- browser backend token usage is not exact
- one browser worker / serialized queue by default
- no shell/filesystem/MCP tool loop yet
- no browser pool or session pool yet

## License

MIT
