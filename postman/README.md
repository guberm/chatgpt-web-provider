# Postman project for chatgpt-web-provider

Import these two files into Postman:

1. `chatgpt-web-provider.postman_collection.json`
2. `chatgpt-web-provider.template.postman_environment.json`

Set environment variable `api_key` to your live `X-API-Key` before running authenticated requests.

The collection sets `User-Agent: {{user_agent}}` with default `PostmanRuntime/7.45.0`; Cloudflare currently blocks Python's default `urllib` user agent, while Postman/curl-style user agents pass.

The public template intentionally does not contain secrets.

Requests included:

- `GET /health`
- `GET /v1/models`
- `GET /v1/provider/status`
- `POST /v1/chat/completions` non-stream
- `POST /v1/chat/completions` stream SSE
- `POST /v1/responses`

## Starting a fresh ChatGPT session

For the browser backend, requests normally continue whatever ChatGPT conversation the browser worker is on. To force a fresh ChatGPT conversation, use either:

```json
"new_session": true
```

in the request body, or this header:

```http
X-New-Session: true
```

The collection includes `Chat Completions - new session` as a ready-to-run example.
