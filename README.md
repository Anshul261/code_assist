# Code Assist LangGraph Prototype

This root project is now the new LangGraph-based agent prototype. The previous Agno/UI code has been moved into `archive/`.

The active browser UI is in `langgraph_assist/templates/index.html`, with the signed-out page in `langgraph_assist/templates/signed-out.html`.

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
export WORKOS_COOKIE_PASSWORD="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

In WorkOS, add this redirect URI:

```text
Redirect URI: http://127.0.0.1:7789/auth/callback
```

Start the local API:

```bash
uv run uvicorn langgraph_assist.app:app --reload --port 7789
```

Open the browser UI:

```text
http://127.0.0.1:7789/
```

The API docs are still available at:

```text
http://127.0.0.1:7789/docs
```

Local testing still works without auth. If `APP_BASE_URL` is left as the local default and Railway is not detected, auth is not required and the in-app model configuration form remains enabled.

### Run Locally With Docker And WorkOS

Expose the Docker image on local port `7789` so it uses the same WorkOS redirect URI as the direct local run:

```text
Redirect URI: http://127.0.0.1:7789/auth/callback
```

Build the local image:

```bash
docker build --tag code-assist:local .
```

When using Docker's `--env-file`, do not wrap values in shell-style quotes. For example:

```dotenv
AUTH_ENABLED=true
APP_BASE_URL=http://127.0.0.1:7789
LANGGRAPH_MODEL_PROVIDER=openrouter
LANGGRAPH_MODEL=openai/gpt-4o-mini
OPENROUTER_API_KEY=sk-or-v1-...
```

Passing `APP_BASE_URL="http://127.0.0.1:7789"` through Docker can make WorkOS receive the invalid callback URL `"http://127.0.0.1:7789"/auth/callback`. Passing `OPENROUTER_API_KEY="sk-or-..."` can similarly cause the provider to reject the quoted key with a `401` authentication error.

If `.env` contains the model and WorkOS settings, start the container with:

```bash
docker run --detach \
  --name code-assist-local \
  --env-file .env \
  --env AUTH_ENABLED=true \
  --env APP_BASE_URL=http://127.0.0.1:7789 \
  --publish 7789:8080 \
  --volume code-assist-local-data:/data \
  --restart unless-stopped \
  code-assist:local
```

If the WorkOS/session values are already exported in your shell rather than stored in `.env`, pass those named variables through without printing them:

```bash
docker run --detach \
  --name code-assist-local \
  --env-file .env \
  --env AUTH_ENABLED=true \
  --env APP_BASE_URL=http://127.0.0.1:7789 \
  --env WORKOS_API_KEY \
  --env WORKOS_CLIENT_ID \
  --env SESSION_SECRET \
  --env WORKOS_COOKIE_PASSWORD \
  --publish 7789:8080 \
  --volume code-assist-local-data:/data \
  --restart unless-stopped \
  code-assist:local
```

Verify the service and open it:

```bash
curl http://127.0.0.1:7789/health
```

```text
http://127.0.0.1:7789/
```

To replace an existing local container after a rebuild while retaining application data in the named volume:

```bash
docker rm --force code-assist-local
```

Then run the relevant `docker run` command again.

## Railway Deployment Security

For a public Railway deployment, set up WorkOS before exposing the app. The app treats HTTPS/Railway as auth-required and fails closed with `503` if its auth configuration is missing.

### Deploy To Railway

1. Push this repository to a private GitHub repository and create a Railway service from it. Railway uses `Dockerfile` and `railway.toml`.
2. Generate a Railway public domain, or attach your own HTTPS domain.
3. Create a Railway volume mounted at:

   ```text
   /data
   ```

   The app stores per-user uploads, generated downloads, memory, and LangGraph checkpoints under `/data/lg_workspace`. Use one application replica while using this SQLite/volume storage model.
4. Set `RAILWAY_RUN_UID=0`. Railway mounts volumes owned by root; the hardened entrypoint uses root only to give `/data/lg_workspace` to the unprivileged `app` user, then runs Uvicorn as `app` (UID `10001`).
5. Set the service variables below. Generate secrets locally; do not commit them.

```bash
RAILWAY_RUN_UID=0
AUTH_ENABLED=true
APP_BASE_URL="https://your-app.up.railway.app"
WORKOS_API_KEY="..."
WORKOS_CLIENT_ID="..."
SESSION_SECRET="a-32-byte-or-longer-random-secret"
WORKOS_COOKIE_PASSWORD="a-fernet-key-generated-as-shown-below"
OPENAI_API_KEY="..."
# or OPENROUTER_API_KEY="..."
LANGGRAPH_MODEL_PROVIDER="openai"
LANGGRAPH_MODEL="gpt-4o-mini"
MAX_UPLOAD_MB=25
MAX_USER_STORAGE_MB=250
CHAT_REQUESTS_PER_MINUTE=12
UPLOAD_REQUESTS_PER_MINUTE=6
```

Generate new values locally:

```bash
openssl rand -hex 32
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Use the first output for `SESSION_SECRET` and the second for `WORKOS_COOKIE_PASSWORD`.

6. In WorkOS, add production redirects:

```text
Redirect URI: https://your-app.up.railway.app/auth/callback
Sign-in endpoint: https://your-app.up.railway.app/auth/login
Sign-out redirect: https://your-app.up.railway.app/signed-out
```

7. In WorkOS, keep public sign-up disabled, invite allowed users manually, enable MFA, and leave impersonation off. AuthKit handles TOTP enrollment and verification in the hosted login flow.
8. Deploy and verify:

   ```text
   /health       responds without authentication for Railway health checks
   /             redirects to WorkOS until signed in
   /outputs      lists only the signed-in user's generated files
   /download/... downloads only files from that signed-in user's output directory
   ```

Security defaults for public deploys:

- Auth is required on Railway/HTTPS.
- WorkOS sessions are stored in an encrypted sealed-session cookie and validated from WorkOS-issued tokens.
- OAuth login uses a state value to prevent login CSRF.
- User uploads, outputs, memory, and LangGraph checkpoints are separated by authenticated user.
- Runtime model/API-key changes are disabled unless `ALLOW_RUNTIME_MODEL_CONFIG=true`.
- Uploads are capped at 25 MB by default; set `MAX_UPLOAD_MB` to change this.
- Each user's upload/output/scratch storage is capped at 250 MB by default; set `MAX_USER_STORAGE_MB` to change this.
- Chat and uploads are throttled per authenticated user.
- The URL fetch tool blocks private/non-public network destinations and bounds fetched content.
- Browser security headers and safer assistant Markdown links are enabled.
- API responses no longer expose server absolute file paths.

Container controls:

- Multi-stage image: dependencies are built separately and only the application runtime is shipped.
- Minimal Debian slim runtime with no development server/reloader.
- Application files are owned by and readable by the unprivileged `app` account; generated data is written only to `/data/lg_workspace`.
- `tini` handles process signals and `gosu` drops root after Railway volume ownership initialization.
- The web server and all agent/tool processing run as non-root UID `10001`.
- Do not mount Docker sockets or any additional host paths into this service.

Railway does not expose every Docker runtime hardening flag through this repository configuration. If you later deploy the image on a runtime you control, additionally run it with a read-only root filesystem, `--cap-drop=ALL`, and `--security-opt=no-new-privileges`; keep writable mounts limited to `/data` and temporary storage.

## Local Storage

- Uploads: `lg_workspace/uploads`
- Generated files: `lg_workspace/outputs`
- LangGraph checkpoints and memory: `lg_workspace/state`

`lg_workspace/` is ignored by git.

## Cloudflare Access

Cloudflare Access can be a good outer access gate for a small private app, particularly when your domain is already on Cloudflare. Do not treat it as a drop-in replacement while the Railway public origin remains accessible: direct requests to the Railway domain bypass Cloudflare unless the app verifies Cloudflare Access JWTs or the origin is only reachable through a Cloudflare Tunnel.

For this app, WorkOS remains the simpler primary identity layer because per-user storage and downloads require a trusted user identity inside the application. Cloudflare Access can be added later as an additional perimeter control, or replace WorkOS only after implementing Access JWT validation and preventing origin bypass.
