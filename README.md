# chatgpt-web-provider

OpenAI-compatible API facade for a browser-controlled `chatgpt.com` worker.

This project is designed for personal/internal use: third-party tools call a normal
OpenAI-style HTTP API, while a local browser worker sends prompts to ChatGPT.com
behind the scenes.

> Status: MVP. The API/auth/service scaffolding is working. The browser backend
> is intentionally conservative and requires a logged-in dedicated Chrome profile.
> Do not expose this as a public paid API and review ChatGPT/OpenAI terms before use.

## Features

- `GET /health`
- `GET /v1/models`
- `GET /v1/provider/status`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- Bearer-token auth and `X-API-Key` support
- mock backend for tests/local smoke checks
- browser backend skeleton using Playwright persistent Chromium profile
- simple in-process request queue with provider status endpoint
- secret redaction helpers
- systemd and Caddy deployment examples

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env
python -m pytest
CHATGPT_WEB_API_KEYS=dev-token CHATGPT_WEB_BACKEND=mock chatgpt-web-provider
```

Smoke test:

```bash
curl -s http://127.0.0.1:8791/health
curl -s -H 'X-API-Key: REPLACE_ME' http://127.0.0.1:8791/v1/models
curl -s -H 'X-API-Key: REPLACE_ME' \
  -H 'Content-Type: application/json' \
  http://127.0.0.1:8791/v1/chat/completions \
  -d '{"model":"chatgpt-5.5-high-web","messages":[{"role":"user","content":"Say pong"}]}'
curl -s -H 'X-API-Key: REPLACE_ME' http://127.0.0.1:8791/v1/provider/status
```

## Browser backend

Set:

```bash
CHATGPT_WEB_BACKEND=browser
CHATGPT_WEB_PROFILE_DIR=$HOME/.local/share/chatgpt-web-provider/chrome-profile
CHATGPT_WEB_HEADLESS=false   # first login/setup only
```

Start once with a visible browser, log in to ChatGPT.com in the dedicated profile,
select the desired model (for example GPT-5.5 High), then restart with
`CHATGPT_WEB_HEADLESS=true` if your environment supports headless execution.

The browser backend is the fragile part: ChatGPT UI selectors and internal behavior
can change at any time. Keep it isolated from your normal browser profile.

## Security model

Default intended deployment:

- bind app to `127.0.0.1`
- expose through your own reverse proxy only when protected by API keys and/or
  additional access controls
- use a dedicated ChatGPT browser profile
- never mount `~/.ssh`, `~/.hermes/.env`, customer projects, or production secrets
  into browser/tool workers by default
- do not auto-confirm high-impact shell/MCP actions

This repo does not provide shell/MCP tools yet. Add those behind explicit allowlists,
argument schemas, approval gates, and audit logs.

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

## License

MIT
