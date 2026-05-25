from __future__ import annotations

import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response

from .agent import LangGraphAgent, ModelConfig
from .runlog import append_log, get_logs
from .sandbox import Sandbox, sandbox_from_env


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"
SIGNED_OUT_HTML_PATH = TEMPLATES_DIR / "signed-out.html"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(default="default", min_length=1, max_length=80)


class ModelConfigRequest(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(max_length=120)
    api_key: str = Field(default="", max_length=400)
    temperature: float = Field(default=0.2, ge=0, le=2)


base_sandbox = sandbox_from_env()
_agents: dict[str, LangGraphAgent] = {}
_model_config = ModelConfig.from_env()
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
WORKOS_API_KEY = os.getenv("WORKOS_API_KEY", "").strip()
WORKOS_CLIENT_ID = os.getenv("WORKOS_CLIENT_ID", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:7789").rstrip("/")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-secret-change-me")
SESSION_SECRET_READY = bool(os.getenv("SESSION_SECRET"))
WORKOS_COOKIE_PASSWORD = os.getenv("WORKOS_COOKIE_PASSWORD", "").strip()
AUTH_READY = bool(WORKOS_API_KEY and WORKOS_CLIENT_ID and SESSION_SECRET_READY and WORKOS_COOKIE_PASSWORD)
PUBLIC_DEPLOYMENT = APP_BASE_URL.startswith("https://") or bool(os.getenv("RAILWAY_ENVIRONMENT"))
AUTH_REQUIRED = AUTH_ENABLED or PUBLIC_DEPLOYMENT
ALLOW_RUNTIME_MODEL_CONFIG = os.getenv(
    "ALLOW_RUNTIME_MODEL_CONFIG",
    "false" if PUBLIC_DEPLOYMENT else "true",
).lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_USER_STORAGE_BYTES = int(os.getenv("MAX_USER_STORAGE_MB", "250")) * 1024 * 1024
CHAT_REQUESTS_PER_MINUTE = int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "12"))
UPLOAD_REQUESTS_PER_MINUTE = int(os.getenv("UPLOAD_REQUESTS_PER_MINUTE", "6"))
SAFE_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
WORKOS_SESSION_COOKIE = "wos_session"
_rate_events: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()
CORS_ORIGINS = [APP_BASE_URL]
if not PUBLIC_DEPLOYMENT:
    CORS_ORIGINS.extend(
        [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ]
    )

workos_client = WorkOSClient(api_key=WORKOS_API_KEY, client_id=WORKOS_CLIENT_ID) if AUTH_READY else None

app = FastAPI(title="Code Assist LangGraph Prototype")


def auth_missing_detail() -> str:
    return (
        "Auth is enabled but WORKOS_API_KEY, WORKOS_CLIENT_ID, SESSION_SECRET, "
        "or WORKOS_COOKIE_PASSWORD is missing."
    )


def workos_user_payload(user) -> dict[str, str]:
    def value(field: str) -> str:
        if isinstance(user, dict):
            return str(user.get(field) or "")
        return str(getattr(user, field, "") or "")

    first_name = value("first_name")
    last_name = value("last_name")
    email = value("email")
    name = " ".join(part for part in [first_name, last_name] if part).strip()
    return {
        "sub": value("id") or email,
        "name": name or email or "Authenticated user",
        "email": email,
        "picture": value("profile_picture_url"),
    }


def set_workos_cookie(response, value: str) -> None:
    response.set_cookie(
        WORKOS_SESSION_COOKIE,
        value,
        httponly=True,
        secure=PUBLIC_DEPLOYMENT,
        samesite="lax",
        max_age=60 * 60 * 12,
    )


def authenticate_workos_request(request: Request) -> str | None:
    sealed_session = request.cookies.get(WORKOS_SESSION_COOKIE, "")
    if not sealed_session or workos_client is None:
        return None
    session = workos_client.user_management.load_sealed_session(
        session_data=sealed_session,
        cookie_password=WORKOS_COOKIE_PASSWORD,
    )
    auth_response = session.authenticate()
    if auth_response.authenticated and auth_response.user:
        request.state.user = workos_user_payload(auth_response.user)
        request.state.workos_session = session
        return None
    refreshed = session.refresh()
    if refreshed.authenticated and refreshed.user:
        request.state.user = workos_user_payload(refreshed.user)
        request.state.workos_session = session
        return refreshed.sealed_session
    return None


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if AUTH_REQUIRED and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not _request_origin_allowed(request):
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
    if not AUTH_REQUIRED:
        return await call_next(request)
    public_paths = {
        "/auth/login",
        "/auth/callback",
        "/auth/logout",
        "/favicon.ico",
        "/health",
        "/signed-out",
    }
    if request.url.path in public_paths:
        return await call_next(request)
    if not AUTH_READY:
        return JSONResponse(
            status_code=503,
            content={"detail": auth_missing_detail()},
        )
    refreshed_session = authenticate_workos_request(request)
    if getattr(request.state, "user", None):
        response = await call_next(request)
        if refreshed_session:
            set_workos_cookie(response, refreshed_session)
        return response
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/auth/login")
    return JSONResponse(status_code=401, content={"detail": "Authentication required"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=APP_BASE_URL.startswith("https://"),
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data: https:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if PUBLIC_DEPLOYMENT:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if AUTH_REQUIRED and request.url.path not in {"/favicon.ico"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/auth/login")
async def auth_login(request: Request):
    if not AUTH_REQUIRED:
        return RedirectResponse(url="/")
    if not AUTH_READY:
        raise HTTPException(status_code=503, detail=auth_missing_detail())
    redirect_uri = f"{APP_BASE_URL}/auth/callback"
    if workos_client is None:
        raise HTTPException(status_code=503, detail=auth_missing_detail())
    authorization_url = workos_client.user_management.get_authorization_url(
        provider="authkit",
        redirect_uri=redirect_uri,
        state=(state := secrets.token_urlsafe(32)),
    )
    request.session["oauth_state"] = state
    return RedirectResponse(url=authorization_url)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    if not AUTH_READY:
        raise HTTPException(status_code=503, detail=auth_missing_detail())
    if workos_client is None:
        raise HTTPException(status_code=503, detail=auth_missing_detail())
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    expected_state = request.session.pop("oauth_state", "")
    received_state = request.query_params.get("state", "")
    if not expected_state or not secrets.compare_digest(expected_state, received_state):
        raise HTTPException(status_code=400, detail="Invalid authentication state")
    auth_response = workos_client.user_management.authenticate_with_code(code=code)
    sealed_session = seal_session_from_auth_response(
        access_token=auth_response.access_token,
        refresh_token=auth_response.refresh_token,
        user=auth_response.user.to_dict(),
        cookie_password=WORKOS_COOKIE_PASSWORD,
    )
    request.session.clear()
    response = RedirectResponse(url="/")
    set_workos_cookie(response, sealed_session)
    return response


@app.get("/auth/logout")
async def auth_logout(request: Request):
    sealed_session = request.cookies.get(WORKOS_SESSION_COOKIE, "")
    request.session.clear()
    logout_url = "/signed-out"
    if AUTH_READY and workos_client is not None and sealed_session:
        session = workos_client.user_management.load_sealed_session(
            session_data=sealed_session,
            cookie_password=WORKOS_COOKIE_PASSWORD,
        )
        try:
            logout_url = session.get_logout_url(return_to=f"{APP_BASE_URL}/signed-out")
        except ValueError:
            pass
    response = RedirectResponse(url=logout_url)
    response.delete_cookie(WORKOS_SESSION_COOKIE)
    return response


@app.get("/auth/me")
def auth_me(request: Request) -> dict:
    return {
        "auth_enabled": AUTH_REQUIRED,
        "auth_ready": AUTH_READY,
        "provider": "workos",
        "user": getattr(request.state, "user", None),
        "runtime_model_config_allowed": ALLOW_RUNTIME_MODEL_CONFIG,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(INDEX_HTML_PATH, media_type="text/html")


@app.get("/signed-out", response_class=HTMLResponse)
def signed_out():
    return FileResponse(SIGNED_OUT_HTML_PATH, media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/model-config")
def get_model_config() -> dict[str, str | bool | float]:
    return {
        "provider": _model_config.provider,
        "model": _model_config.model,
        "temperature": _model_config.temperature,
        "api_key_set": bool(_model_config.api_key),
        "runtime_updates_allowed": ALLOW_RUNTIME_MODEL_CONFIG,
    }


@app.post("/api/model-config")
def update_model_config(request: ModelConfigRequest) -> dict[str, str | bool | float]:
    global _agents, _model_config
    if not ALLOW_RUNTIME_MODEL_CONFIG:
        raise HTTPException(
            status_code=403,
            detail="Runtime model changes are disabled for this deployment. Configure provider keys in Railway instead.",
        )
    provider = request.provider.strip().lower()
    if provider not in {"openrouter", "openai"}:
        raise HTTPException(status_code=400, detail="provider must be openrouter or openai")
    if not request.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    api_key = request.api_key.strip() or _model_config.api_key
    _model_config = ModelConfig(
        provider=provider,
        model=request.model.strip(),
        api_key=api_key,
        temperature=request.temperature,
    )
    _agents = {}
    return {
        "provider": _model_config.provider,
        "model": _model_config.model,
        "temperature": _model_config.temperature,
        "api_key_set": bool(_model_config.api_key),
        "status": "ok",
    }


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> dict[str, str | int]:
    enforce_rate_limit(request, "upload", UPLOAD_REQUESTS_PER_MINUTE)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
        )
    active_sandbox = sandbox_for_request(request)
    enforce_storage_quota(active_sandbox, additional_bytes=len(data))
    saved = active_sandbox.save_upload(file.filename or f"upload-{uuid4().hex}", data)
    return {
        "status": "success",
        "filename": saved.name,
        "path": str(saved.relative_to(active_sandbox.uploads_dir)),
        "size": saved.stat().st_size,
    }


@app.get("/uploads")
def list_uploads(request: Request) -> list[dict[str, str | int]]:
    active_sandbox = sandbox_for_request(request)
    active_sandbox.ensure()
    uploads = []
    for path in sorted(active_sandbox.uploads_dir.rglob("*")):
        if path.is_file():
            uploads.append(
                {
                    "path": str(path.relative_to(active_sandbox.uploads_dir)),
                    "size": path.stat().st_size,
                }
            )
    return uploads


@app.post("/chat")
def chat(payload: ChatRequest, request: Request) -> dict:
    enforce_rate_limit(request, "chat", CHAT_REQUESTS_PER_MINUTE)
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    session_id = validate_session_id(payload.session_id)
    scoped_session_id = scoped_run_id(request, session_id)
    enforce_storage_quota(sandbox_for_request(request))
    try:
        return get_agent(request).invoke(payload.message, session_id=scoped_session_id)
    except RuntimeError as exc:
        append_log("error", "Runtime error", str(exc), session_id=scoped_session_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        append_log("error", "Agent error", str(exc), session_id=scoped_session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/runs/{session_id}/logs")
def run_logs(session_id: str, request: Request) -> list[dict]:
    return get_logs(scoped_run_id(request, validate_session_id(session_id)))


@app.get("/outputs")
def list_outputs(request: Request) -> list[dict[str, str | int]]:
    return sandbox_for_request(request).list_outputs()


@app.get("/download/{artifact_path:path}")
def download(artifact_path: str, request: Request):
    try:
        path = sandbox_for_request(request).resolve_output(artifact_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(
        str(path),
        filename=Path(path).name,
        headers={"Cache-Control": "private, no-store"},
    )


def get_agent(request: Request) -> LangGraphAgent:
    key = user_storage_key(request)
    if key not in _agents:
        _agents[key] = LangGraphAgent(sandbox=sandbox_for_request(request), model_config=_model_config)
    return _agents[key]


def sandbox_for_request(request: Request) -> Sandbox:
    if not AUTH_REQUIRED:
        return base_sandbox
    return Sandbox(root=base_sandbox.root / "users" / user_storage_key(request))


def user_storage_key(request: Request) -> str:
    if not AUTH_REQUIRED:
        return "local"
    user = getattr(request.state, "user", None) or {}
    subject = str(user.get("sub") or user.get("email") or "")
    if not subject:
        raise HTTPException(status_code=401, detail="Authentication required")
    import hashlib

    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:24]


def scoped_run_id(request: Request, session_id: str) -> str:
    return f"{user_storage_key(request)}:{session_id}" if AUTH_REQUIRED else session_id


def validate_session_id(session_id: str) -> str:
    if not SAFE_SESSION_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="session_id may only contain letters, numbers, dot, underscore, and dash")
    return session_id


def enforce_rate_limit(request: Request, action: str, limit: int) -> None:
    if not AUTH_REQUIRED or limit <= 0:
        return
    key = f"{user_storage_key(request)}:{action}"
    now = time.monotonic()
    window_start = now - 60
    with _rate_lock:
        events = _rate_events[key]
        while events and events[0] <= window_start:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Too many {action} requests. Try again shortly.",
                headers={"Retry-After": "60"},
            )
        events.append(now)


def enforce_storage_quota(sandbox: Sandbox, additional_bytes: int = 0) -> None:
    if MAX_USER_STORAGE_BYTES <= 0:
        return
    if sandbox.storage_size() + additional_bytes > MAX_USER_STORAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="User storage limit reached. Contact the administrator to clean up stored artifacts.",
        )


def _request_origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return True
    if _same_origin(origin, APP_BASE_URL):
        return True
    return not PUBLIC_DEPLOYMENT and _same_origin(
        origin, f"{request.url.scheme}://{request.url.netloc}"
    )


def _same_origin(candidate: str, expected: str) -> bool:
    candidate_url = urlparse(candidate)
    expected_url = urlparse(expected)
    return (
        candidate_url.scheme == expected_url.scheme
        and candidate_url.hostname == expected_url.hostname
        and (candidate_url.port or _default_port(candidate_url.scheme))
        == (expected_url.port or _default_port(expected_url.scheme))
    )


def _default_port(scheme: str) -> int | None:
    return 443 if scheme == "https" else 80 if scheme == "http" else None
