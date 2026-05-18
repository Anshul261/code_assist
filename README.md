# Code Assist LangGraph Prototype

This root project is now the new LangGraph-based agent prototype. The previous Agno/UI code has been moved into `archive/`.

## Run

Set one model provider:

```bash
export OPENAI_API_KEY="..."
export LANGGRAPH_MODEL="gpt-4o-mini"
```

or:

```bash
export OPENROUTER_API_KEY="..."
export LANGGRAPH_MODEL_PROVIDER="openrouter"
export LANGGRAPH_MODEL="openai/gpt-4o-mini"
```

## Auth

Auth is off by default for local development. The project uses WorkOS AuthKit as the single auth provider because it has the best free-tier fit for this app: hosted login, a Python SDK, and free WorkOS User Management for up to 1 million monthly active users.

Create a WorkOS application and set:

```bash
export AUTH_ENABLED=true
export WORKOS_API_KEY="..."
export WORKOS_CLIENT_ID="..."
export APP_BASE_URL="http://127.0.0.1:7789"
export SESSION_SECRET="$(openssl rand -hex 32)"
```

In WorkOS, add this redirect URI:

```text
Redirect URI: http://127.0.0.1:7789/auth/callback
```

Start the local API:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn langgraph_assist.app:app --reload --port 7789
```

Open the browser UI:

```text
http://localhost:7789/
```

The API docs are still available at:

```text
http://localhost:7789/docs
```

Local testing still works without auth. If `APP_BASE_URL` is left as the local default and Railway is not detected, auth is not required and the in-app model configuration form remains enabled.

## Railway Deployment Security

For a public Railway deployment, set up WorkOS before exposing the app. The app treats HTTPS/Railway as auth-required and fails closed with `503` if WorkOS or the session secret is missing.

Minimum Railway variables:

```bash
AUTH_ENABLED=true
APP_BASE_URL="https://your-app.up.railway.app"
WORKOS_API_KEY="..."
WORKOS_CLIENT_ID="..."
SESSION_SECRET="a-32-byte-or-longer-random-secret"
OPENAI_API_KEY="..."
# or OPENROUTER_API_KEY="..."
```

In WorkOS:

```text
Redirect URI: https://your-app.up.railway.app/auth/callback
```

Enable MFA from the WorkOS Dashboard Authentication settings. AuthKit handles TOTP enrollment and verification in the hosted login flow, so the app does not need to store MFA secrets.

Security defaults for public deploys:

- Auth is required on Railway/HTTPS.
- User uploads, outputs, memory, and LangGraph checkpoints are separated by authenticated user.
- Runtime model/API-key changes are disabled unless `ALLOW_RUNTIME_MODEL_CONFIG=true`.
- Uploads are capped at 25 MB by default; set `MAX_UPLOAD_MB` to change this.
- API responses no longer expose server absolute file paths.

## Local Storage

- Uploads: `lg_workspace/uploads`
- Generated files: `lg_workspace/outputs`
- LangGraph checkpoints and memory: `lg_workspace/state`

`lg_workspace/` is ignored by git.
