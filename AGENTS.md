# Code Assist Agent Notes

This repo contains the active LangGraph-based agent prototype in `langgraph_assist/`. The older Agno/Next.js implementation lives under `archive/` and should be treated as reference material only unless the user explicitly asks to revive it.

## Operating Rules For Future Agents

- Do not read environment variables, `.env` contents, secrets, deployment variables, or machine-specific env details. Ask the user to check or set values when needed.
- Prefer researching existing tools, libraries, and established solutions before making complex architectural changes.
- Keep local development easy. Security changes for public deployment must not break the default local flow.
- Treat this as a public-facing AI-agent app when making deployment decisions.
- Avoid leaking server absolute paths, secrets, provider API keys, user files, or cross-user state through API responses, logs, prompts, or generated artifacts.

## Current Runtime Architecture

The active runtime is:

- `langgraph_assist/app.py`: FastAPI HTTP app, auth middleware, uploads, downloads, chat endpoints, model configuration, per-user sandbox/agent selection.
- `langgraph_assist/templates/index.html`: Browser chat workspace UI, client-side session state, and API interactions.
- `langgraph_assist/templates/signed-out.html`: Post-logout page.
- `langgraph_assist/agent.py`: LangGraph ReAct agent construction, LLM provider setup, system prompt, SQLite checkpointer, memory store, tool wiring.
- `langgraph_assist/tools.py`: LangChain tool definitions exposed to the LLM.
- `langgraph_assist/sandbox.py`: App-level file path confinement helper for uploads, outputs, scratch, checkpoints, and memory DB paths.
- `langgraph_assist/memory.py`: Long-term SQLite memory store.
- `langgraph_assist/runlog.py`: In-memory per-session run activity logs shown in the UI.
- `langgraph_assist/cli.py`: Local CLI entrypoint for invoking the agent.

The browser UI is served from static HTML templates. It stores local UI sessions in browser `localStorage`, calls the FastAPI endpoints, polls activity logs, and renders output download links.

## LLM And Agent Flow

The agent is built with `langgraph.prebuilt.create_react_agent`.

Flow:

1. User opens `/`; FastAPI serves the inline UI.
2. UI sends `POST /chat` with `message` and `session_id`.
3. `app.py` validates the message and session id.
4. `get_agent(request)` returns a cached `LangGraphAgent` for the current local/public user scope.
5. `LangGraphAgent.invoke(...)` starts run logging, invokes the LangGraph graph, and returns the final model response plus current outputs.
6. The UI renders the response and polls `/api/runs/{session_id}/logs` while work is running.

LLM provider logic is in `ModelConfig.from_env()` and `LangGraphAgent._build_model()`:

- OpenRouter is used when configured as provider or when the OpenRouter key is present.
- OpenAI is the other supported provider.
- The app supports runtime provider/model updates locally.
- For public auth-required deployments, runtime model/API-key updates are disabled by default because they affect shared server state.

Do not add provider-specific secrets to client-side state. Public deployments should configure provider keys in Railway variables.

## Chat, Sessions, And Checkpointing

There are two session concepts:

- UI sessions: stored in browser `localStorage`; these control what the browser displays.
- LangGraph thread sessions: passed to LangGraph as `thread_id`; these control checkpoint continuity.

Locally, the session id is used as provided after validation. In auth-required public mode, the runtime scopes thread ids as:

```text
<hashed-user-id>:<session-id>
```

LangGraph checkpoints are persisted to SQLite:

```text
lg_workspace/state/langgraph.sqlite
```

In public per-user mode:

```text
lg_workspace/users/<hashed-user-id>/state/langgraph.sqlite
```

The run log in `runlog.py` is not durable. It is process memory used for live UI activity updates only.

## Long-Term Memory

Long-term memory is implemented by `MemoryStore` in `memory.py`.

Current schema:

```sql
memories (
  id integer primary key autoincrement,
  namespace text not null,
  content text not null,
  created_at datetime default current_timestamp
)
```

The agent exposes two memory tools:

- `remember(namespace, content)`: insert a durable memory row.
- `search_memory(namespace, query, limit)`: SQL `LIKE` search within a namespace, newest first.

This is durable SQLite memory, not vector/semantic memory. It only writes when the model chooses to call `remember`, usually guided by the system prompt or an explicit user request. It only reads when the model chooses to call `search_memory`.

Storage paths:

```text
lg_workspace/state/memory.sqlite
lg_workspace/users/<hashed-user-id>/state/memory.sqlite
```

Deployment note: Railway needs persistent storage/volume if these SQLite files should survive redeploys or container replacement.

Future memory improvements:

- Add automatic post-run memory extraction.
- Add explicit memory update/delete tools.
- Add a user-visible memory management UI.
- Add memory types such as `preference`, `project_fact`, `decision`, and `personalization`.
- Add semantic search with embeddings or a hosted vector store if needed.
- Add stricter rules for sensitive data so credentials and private keys are never remembered.

## Storage Layout

Default local storage:

```text
lg_workspace/
  uploads/
  outputs/
  scratch/
  state/
    langgraph.sqlite
    memory.sqlite
```

Public auth-required storage:

```text
lg_workspace/users/<hashed-user-id>/
  uploads/
  outputs/
  scratch/
  state/
    langgraph.sqlite
    memory.sqlite
```

Uploads and generated artifacts should stay inside this tree. Do not return absolute server paths from HTTP APIs.

## Current Tools

Tools are defined in `build_tools(sandbox, memory)`.

Operational/logging:

- `think(title, thought, action, confidence)`: records a concise progress plan in run logs.
- `analyze(title, result, analysis, next_action, confidence)`: records a concise result checkpoint in run logs.

File tools:

- `list_uploaded_files()`: lists files under sandbox uploads.
- `read_text_file(path, max_chars)`: reads text/PDF/DOCX/PPTX/XLSX/CSV/Markdown from the sandbox.
- `write_markdown(filename, content)`: writes `.md` or `.txt` under sandbox outputs.

Research tools:

- `duckduckgo_search(query, max_results)`: web search via `ddgs`.
- `fetch_url(url, max_chars)`: fetches a URL via `httpx`.

Artifact tools:

- `create_word_doc(filename, title, sections_json)`: creates a basic DOCX.
- `create_analyst_word_report(filename, report_json)`: creates a styled analyst-style DOCX.
- `create_powerpoint(filename, title, slides_json)`: creates a PPTX deck.
- `create_excel_workbook(filename, sheets_json)`: creates XLSX.
- `run_ppt_skill(markdown_outline, output_name)`: creates a PPTX from markdown outline using local parsing/generation.

Memory tools:

- `remember(namespace, content)`.
- `search_memory(namespace, query, limit)`.

Current important absence: there is no shell execution tool exposed to the LLM. Preserve that default unless a proper OS sandbox is introduced.

## Current Sandbox Behavior

`sandbox.py` is an app-level path confinement helper. It is not an OS/process/container sandbox.

It provides:

- `resolve_read(raw_path)`: permits reads only from uploads, outputs, or scratch.
- `resolve_output(raw_path)`: resolves writes under outputs.
- `resolve_scratch(raw_path)`: resolves writes under scratch.
- `save_upload(filename, data)`: writes sanitized upload names under uploads.
- `list_outputs()`: lists generated outputs with relative paths and download URLs.
- `copy_into_outputs(source, output_name)`: copies a server-side source file into outputs.

The sandbox protects against path traversal in app-controlled file operations. It does not stop arbitrary code execution if a future tool runs shell/Python outside constraints. If file-system or execution tools are added, introduce a real sandbox first.

## Auth And WorkOS Plan

WorkOS AuthKit is the intended auth provider for public deployment.

Current auth routes:

- `GET /auth/login`: redirect to WorkOS hosted AuthKit login.
- `GET /auth/callback`: validate OAuth state, exchange code, and set an encrypted WorkOS sealed-session cookie.
- `GET /auth/logout`: clear the session cookie and invoke WorkOS session logout.
- `GET /auth/me`: report auth status and current user summary.

Current auth behavior:

- Local default: auth is off unless explicitly enabled.
- Public/Railway/HTTPS: auth is required and the app fails closed if WorkOS config, `SESSION_SECRET`, or `WORKOS_COOKIE_PASSWORD` is missing.
- Public mode uses per-user storage and per-user agent instances.
- Public mode disables runtime model/API-key changes by default.
- Authenticated requests validate WorkOS session tokens through the WorkOS SDK; login uses OAuth state validation.

WorkOS setup still needs to be completed by the user before deployment:

- Create WorkOS application.
- Configure callback URL: `https://<railway-domain>/auth/callback`.
- Set Railway variables for WorkOS client/API credentials, app base URL, session secret, WorkOS cookie password, and model provider key.
- Enable MFA in the WorkOS dashboard. AuthKit should handle hosted TOTP enrollment and verification; the app should not store MFA secrets.

Future auth hardening:

- Add allowed-email or allowed-domain checks for the first private deployment.
- Add explicit admin role logic before exposing runtime model configuration in public mode.
- Consider durable/distributed rate limiting if deployment moves beyond a single Railway volume-backed instance.
- Add audit logs for login, upload, chat start, tool use, and downloads.

## UI State

The current UI is static HTML/JS served by FastAPI and functional, not a full frontend app.

Current UI capabilities:

- Local session list stored in `localStorage`.
- Prompt input and chat rendering.
- Upload input.
- Output list with download links.
- Model config form.
- Auth status line.
- Live run log polling.
- Theme preference in `localStorage`.

Known UI limitations:

- UI sessions are local browser state, not server-side records.
- Memory is not visible or editable by the user.
- Auth UX is minimal.
- Output and upload management is minimal.
- Logs are ephemeral and vanish on process restart.

Future UI upgrades:

- Move UI into a proper frontend if the app grows beyond the prototype.
- Add server-side session list per user.
- Add memory viewer/editor with delete controls.
- Add upload manager with delete, preview, and file type indicators.
- Add admin settings page for model provider, rate limits, and user allowlist.
- Add better error states for auth misconfiguration, provider key failures, and tool failures.
- Add streaming responses instead of single blocking `/chat` responses.

## Future Sandbox And Tooling Direction

Before adding powerful tools such as shell, filesystem mutation, browser automation, repo editing, or Notion write access, add stronger isolation and permissions.

Recommended future sandbox direction:

- Run tool execution in a separate worker process/container.
- Use a per-user working directory with strict mount boundaries.
- Enforce CPU, memory, timeout, file count, and file size limits.
- Separate read-only uploads from writable scratch/outputs.
- Add allowlisted file operations instead of arbitrary paths.
- Scan generated/downloaded files where practical.
- Keep secrets out of the tool environment.
- Add a tool permission layer so high-risk tools require explicit user approval.

Future file-system tools:

- List files in sandbox.
- Read files with size limits.
- Write/patch files only in scratch/outputs or approved project workspaces.
- Delete files only with explicit user confirmation.
- Zip/export outputs.

Future integrations:

- Notion: read/search pages first, then gated write/update tools with explicit user approval.
- Google Drive/Docs/Sheets: read and export artifacts with scoped OAuth.
- Slack/Teams: search/read first, then guarded send tools.
- GitHub: inspect repos/issues/PRs before write permissions.
- Browser/web automation: isolate in a worker with no secrets and bounded network scope.

## Deployment Checklist

Before public Railway deployment:

- WorkOS app is created.
- Callback URL matches the Railway public URL.
- MFA is enabled in WorkOS.
- `AUTH_ENABLED=true`.
- `APP_BASE_URL` is the public HTTPS Railway URL.
- `SESSION_SECRET` is strong and unique.
- Provider API key is configured on Railway.
- Railway persistent volume is configured if long-term memory/checkpoints/files must survive redeploys.
- Railway volume is mounted at `/data`, and `RAILWAY_RUN_UID=0` is set so the hardened entrypoint can initialize volume ownership before dropping to UID `10001`.
- Runtime model config remains disabled unless there is an admin layer.
- Upload size limit is acceptable for the deployment.
- No absolute server paths appear in public API responses.
