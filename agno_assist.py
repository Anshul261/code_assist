import glob as globlib
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass, field

import httpx
from agno.agent import Agent
from agno.compression.manager import CompressionManager
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama
from agno.os import AgentOS
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.toolkit import Toolkit
from dotenv import load_dotenv

load_dotenv()

# Anchor cwd to the script's directory so paths are stable regardless of launch dir
os.chdir(pathlib.Path(__file__).parent)

WORKING_DIR = pathlib.Path.cwd().resolve()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# =============================================================================
# WORKSPACE CONFIG — mutable at runtime via API
# =============================================================================


@dataclass
class WorkspaceConfig:
    """Mutable config for the agent's file access scope."""

    knowledge_dirs: list[pathlib.Path] = field(default_factory=list)
    output_dir: pathlib.Path = field(default_factory=lambda: WORKING_DIR / "output")

    def add_knowledge_dir(self, path: str) -> str:
        p = pathlib.Path(path).resolve()
        if not p.exists():
            return f"error: path does not exist: {path}"
        if not p.is_dir():
            return f"error: path is not a directory: {path}"
        if p not in self.knowledge_dirs:
            self.knowledge_dirs.append(p)
        return "ok"

    def remove_knowledge_dir(self, path: str) -> str:
        p = pathlib.Path(path).resolve()
        if p in self.knowledge_dirs:
            self.knowledge_dirs.remove(p)
            return "ok"
        return f"error: not in knowledge dirs: {path}"

    def set_output_dir(self, path: str) -> str:
        p = pathlib.Path(path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        self.output_dir = p
        return "ok"

    def to_dict(self) -> dict:
        return {
            "knowledge_dirs": [str(d) for d in self.knowledge_dirs],
            "output_dir": str(self.output_dir),
        }


# Initialise from env vars if set
_raw_knowledge = os.getenv("KNOWLEDGE_DIRS", "")
_initial_knowledge = (
    [pathlib.Path(d.strip()).resolve() for d in _raw_knowledge.split(",") if d.strip()]
    if _raw_knowledge
    else [WORKING_DIR]
)
_initial_output = pathlib.Path(
    os.getenv("OUTPUT_DIR", str(WORKING_DIR / "output"))
).resolve()
_initial_output.mkdir(parents=True, exist_ok=True)

workspace = WorkspaceConfig(
    knowledge_dirs=_initial_knowledge,
    output_dir=_initial_output,
)


# =============================================================================
# PATH HELPERS
# =============================================================================


def _within_any(path: pathlib.Path, dirs: list[pathlib.Path]) -> bool:
    for d in dirs:
        try:
            path.relative_to(d)
            return True
        except ValueError:
            continue
    return False


def _resolve_read(path: str) -> pathlib.Path:
    """Resolve a path against knowledge_dirs. Raises ValueError if outside."""
    kdirs = workspace.knowledge_dirs or [WORKING_DIR]
    p = pathlib.Path(path)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        # Search each knowledge dir
        for kd in kdirs:
            candidate = (kd / path).resolve()
            if candidate.exists() and _within_any(candidate, kdirs):
                return candidate
        resolved = (kdirs[0] / path).resolve()
    if not _within_any(resolved, kdirs):
        raise ValueError(
            f"'{path}' is outside knowledge directories: "
            + ", ".join(str(d) for d in kdirs)
        )
    return resolved


def _resolve_write(path: str) -> pathlib.Path:
    """Resolve a path against output_dir. Raises ValueError if outside."""
    out = workspace.output_dir
    p = pathlib.Path(path)
    resolved = (p if p.is_absolute() else out / path).resolve()
    try:
        resolved.relative_to(out)
    except ValueError:
        raise ValueError(f"'{path}' is outside output directory: {out}")
    return resolved


# =============================================================================
# PROVIDER ABSTRACTION
# =============================================================================

PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "status": "active",
        "models_endpoint": "{host}/api/tags",
    },
    "vllm": {
        "name": "vLLM",
        "status": "coming_soon",
        "models_endpoint": "{host}/v1/models",
    },
    "sglang": {
        "name": "SGLang",
        "status": "coming_soon",
        "models_endpoint": "{host}/v1/models",
    },
}


# =============================================================================
# TOOLKITS
# =============================================================================


class FileToolkit(Toolkit):
    """File operations — reads from workspace.knowledge_dirs, writes to workspace.output_dir."""

    def __init__(self, **kwargs):
        tools = [self.ls, self.read, self.write, self.edit, self.glob, self.grep]
        super().__init__(name="file_tools", tools=tools, **kwargs)

    def ls(self, path: str = ".") -> str:
        """List files and directories within the knowledge base.

        Args:
            path: Directory to list. Default: first knowledge directory.

        Returns:
            Directory listing with size/type, or an error.
        """
        try:
            base = _resolve_read(path)
            if not base.exists():
                return f"error: path not found: {path}"
            if base.is_file():
                return str(base)
            entries = sorted(base.iterdir(), key=lambda e: (e.is_file(), e.name))
            lines = []
            for e in entries:
                size = f"{e.stat().st_size:>9}" if e.is_file() else "      DIR"
                lines.append(f"{size}  {e.name}{'/' if e.is_dir() else ''}")
            return "\n".join(lines) or "(empty directory)"
        except Exception as err:
            return f"error: {err}"

    def read(self, path: str = None, offset: int = 0, limit: int = None) -> str:
        """Read a file from the knowledge base and return its contents with line numbers.

        Args:
            path: Path to the file (REQUIRED). Searched across all knowledge dirs.
            offset: Line to start from (0-indexed). Default: 0
            limit: Max lines to read. Default: all

        Returns:
            File contents with line numbers, or an error message.
        """
        if not path:
            return "error: 'path' is required. Example: read(path='notes/report.md')"
        try:
            safe = _resolve_read(path)
            if not safe.exists():
                return f"error: file not found: {path}"
            if safe.is_dir():
                return f"error: path is a directory: {path}"
            lines = safe.read_text(encoding="utf-8").splitlines(keepends=True)
            if limit is None:
                limit = len(lines)
            selected = lines[offset : offset + limit]
            return "".join(
                f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected)
            )
        except Exception as err:
            return f"error: {err}"

    def write(self, path: str = None, content: str = None) -> str:
        """Write content to a file in the output directory.

        Args:
            path: File path relative to output directory (REQUIRED). Example: "reports/summary.md"
            content: Content to write (REQUIRED)

        Returns:
            "ok" on success, or an error message.
        """
        if not path:
            return "error: 'path' is required. Example: write(path='reports/summary.md', content='...')"
        if content is None:
            return "error: 'content' is required."
        try:
            safe = _resolve_write(path)
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return f"ok: wrote {len(content)} chars to {safe}"
        except Exception as err:
            return f"error: {err}"

    def edit(
        self, path: str = None, old: str = None, new: str = None, all: bool = False
    ) -> str:
        """Replace text in a file. Searches knowledge dirs and output dir.

        Args:
            path: Path to the file (REQUIRED)
            old: Exact text to find (REQUIRED)
            new: Replacement text (REQUIRED, can be empty string to delete)
            all: Replace all occurrences. Default: false (requires unique match)

        Returns:
            "ok" on success, or an error message.
        """
        if not path:
            return "error: 'path' is required."
        if old is None:
            return "error: 'old' is required."
        if new is None:
            return "error: 'new' is required."
        try:
            # Prefer output dir (writable), fall back to knowledge dirs
            try:
                safe = _resolve_write(path)
                if not safe.exists():
                    safe = _resolve_read(path)
            except ValueError:
                safe = _resolve_read(path)
            if not safe.exists():
                return f"error: file not found: {path}"
            text = safe.read_text(encoding="utf-8")
            if old not in text:
                return "error: old text not found in file"
            count = text.count(old)
            if not all and count > 1:
                return (
                    f"error: text appears {count} times — use all=true to replace all"
                )
            replacement = text.replace(old, new) if all else text.replace(old, new, 1)
            safe.write_text(replacement, encoding="utf-8")
            return "ok"
        except Exception as err:
            return f"error: {err}"

    def glob(self, pat: str = None, path: str = ".") -> str:
        """Find files matching a glob pattern across all knowledge directories.

        Args:
            pat: Glob pattern (REQUIRED). Examples: "**/*.md", "*.py", "docs/**"
            path: Sub-path to search within each knowledge dir. Default: root

        Returns:
            Newline-separated file paths sorted by modification time, or "none".
        """
        if not pat:
            return "error: 'pat' is required. Example: glob(pat='**/*.md')"
        kdirs = workspace.knowledge_dirs or [WORKING_DIR]
        try:
            found = []
            for kd in kdirs:
                base = (kd / path).resolve() if path != "." else kd
                for f in globlib.glob(str(base / pat), recursive=True):
                    fp = pathlib.Path(f).resolve()
                    if _within_any(fp, kdirs):
                        found.append(f)
            found = sorted(
                set(found),
                key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0,
                reverse=True,
            )
            return "\n".join(found) or "none"
        except Exception as err:
            return f"error: {err}"

    def grep(self, pat: str = None, path: str = ".") -> str:
        """Search file contents for a regex pattern across all knowledge directories.

        Args:
            pat: Regex pattern (REQUIRED). Example: "TODO", "def .*search"
            path: Sub-path to search within. Default: all knowledge dirs

        Returns:
            Matches as "filepath:line_num:content", max 100 results, or "none".
        """
        if not pat:
            return "error: 'pat' is required. Example: grep(pat='search term')"
        try:
            pattern = re.compile(pat, re.IGNORECASE)
        except re.error as e:
            return f"error: invalid regex: {e}"
        kdirs = workspace.knowledge_dirs or [WORKING_DIR]
        try:
            hits = []
            for kd in kdirs:
                base = (kd / path).resolve() if path != "." else kd
                for filepath in globlib.glob(str(base / "**"), recursive=True):
                    fp = pathlib.Path(filepath)
                    if not fp.is_file() or not _within_any(fp, kdirs):
                        continue
                    try:
                        for line_num, line in enumerate(
                            fp.read_text(
                                encoding="utf-8", errors="ignore"
                            ).splitlines(),
                            1,
                        ):
                            if pattern.search(line):
                                hits.append(f"{filepath}:{line_num}:{line.rstrip()}")
                                if len(hits) >= 100:
                                    break
                        if len(hits) >= 100:
                            break
                    except Exception:
                        pass
                if len(hits) >= 100:
                    break
            return "\n".join(hits) or "none"
        except Exception as err:
            return f"error: {err}"


class BashToolkit(Toolkit):
    """Execute shell commands (cwd = WORKING_DIR)."""

    def __init__(self, **kwargs):
        super().__init__(name="bash_tools", tools=[self.bash], **kwargs)

    def bash(self, cmd: str = None, timeout: int = 120) -> str:
        """Execute a shell command and return its output.

        Args:
            cmd: Shell command to run (REQUIRED). Example: "ls -la" or "pip list"
            timeout: Max seconds to wait. Default: 120

        Returns:
            stdout + stderr combined, or an error message.
        """
        if not cmd or not cmd.strip():
            return "error: 'cmd' is required. Example: bash(cmd='ls -la')"
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=WORKING_DIR,
            )
            output_lines = []
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    output_lines.append(line)
            proc.wait(timeout=timeout)
            return "".join(output_lines).strip() or "(empty)"
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"(timed out after {timeout}s)"
        except Exception as err:
            return f"error: {err}"


# =============================================================================
# INSTRUCTIONS
# =============================================================================

CODE_ASSISTANT_INSTRUCTIONS = """You are a local AI assistant that can research topics, read knowledge files, and create documents.

## Research workflow
1. Use `duckduckgo_search` to find information online you can search as much as needed
2. Use `glob` / `grep` to find relevant local files in the knowledge base
3. Use `read` to load file content
4. Synthesise and use `write` to save results to the output directory

## File tools
- `ls(path)` — list a directory
- `glob(pat='**/*.md')` — find files by pattern
- `grep(pat='keyword')` — search file contents
- `read(path='file.md')` — read from knowledge dirs
- `write(path='reports/summary.md', content='...')` — write to output dir
- `edit(path, old, new)` — replace text in a file

## Best practices
- Use grep/glob before reading whole files — find the relevant parts first
- Save research as markdown in the output dir for future reference
- Include sources (URLs) in any reports you write
"""


# =============================================================================
# MODEL FACTORY
# =============================================================================


def get_ollama_models(host: str = None) -> list[dict]:
    base = host or OLLAMA_HOST
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=3)
        resp.raise_for_status()
        return [
            {"id": m["name"], "provider": "ollama", "name": m["name"]}
            for m in resp.json().get("models", [])
        ]
    except Exception:
        return []


def build_model(model_id: str = None, host: str = None):
    model_id = model_id or os.getenv("MODEL", "qwen3.5:9b")
    kwargs = {"id": model_id}
    host = host or OLLAMA_HOST
    if host:
        kwargs["host"] = host
    return Ollama(**kwargs)


# =============================================================================
# AGENT OS
# =============================================================================

DB_PATH = str(WORKING_DIR / "agent_os.db")

db = SqliteDb(db_file=DB_PATH, session_table="agent_sessions")
model = build_model()
compression_manager = CompressionManager(
    model=model,
    compress_tool_results=True,
    compress_tool_results_limit=10,
)

assistant = Agent(
    name="Assistant",
    model=model,
    db=db,
    tools=[
        FileToolkit(),
        BashToolkit(),
        DuckDuckGoTools(enable_search=True, enable_news=True),
    ],
    instructions=CODE_ASSISTANT_INSTRUCTIONS,
    markdown=True,
    compress_tool_results=True,
    compression_manager=compression_manager,
    add_history_to_context=True,
    num_history_runs=10,
    read_chat_history=True,
)

agent_os = AgentOS(
    name="Code Assist",
    agents=[assistant],
    cors_allowed_origins=["http://localhost:3000"],
)

app = agent_os.get_app()


# =============================================================================
# CUSTOM ENDPOINTS
# =============================================================================


@app.get("/api/providers", tags=["Providers"])
async def list_providers():
    return {"providers": PROVIDERS}


@app.get("/api/providers/{provider}/models", tags=["Providers"])
async def list_provider_models(provider: str):
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider: {provider}", "models": []}
    info = PROVIDERS[provider]
    if info["status"] != "active":
        return {"error": f"{info['name']} is {info['status']}", "models": []}
    if provider == "ollama":
        return {"models": get_ollama_models()}
    return {"models": []}


@app.get("/api/available-models", tags=["Models"])
async def list_models():
    current_id = getattr(assistant.model, "id", str(assistant.model))
    return {"models": get_ollama_models(), "current": current_id}


@app.post("/api/switch-model", tags=["Models"])
async def switch_model(body: dict):
    model_id = body.get("model_id")
    if not model_id:
        return {"error": "model_id is required"}
    try:
        new_model = build_model(model_id=model_id)
        assistant.model = new_model
        compression_manager.model = new_model
        return {"status": "ok", "model": model_id}
    except Exception as e:
        return {"error": str(e)}


# --- Workspace endpoints ---


@app.get("/api/workspace", tags=["Workspace"])
async def get_workspace():
    """Return current knowledge dirs and output dir."""
    return workspace.to_dict()


@app.post("/api/workspace/knowledge", tags=["Workspace"])
async def add_knowledge_dir(body: dict):
    """Add a directory to the knowledge base (readable by the agent)."""
    path = body.get("path", "").strip()
    if not path:
        return {"error": "path is required"}
    result = workspace.add_knowledge_dir(path)
    if result == "ok":
        return workspace.to_dict()
    return {"error": result}


@app.delete("/api/workspace/knowledge", tags=["Workspace"])
async def remove_knowledge_dir(body: dict):
    """Remove a directory from the knowledge base."""
    path = body.get("path", "").strip()
    if not path:
        return {"error": "path is required"}
    result = workspace.remove_knowledge_dir(path)
    if result == "ok":
        return workspace.to_dict()
    return {"error": result}


@app.post("/api/workspace/output", tags=["Workspace"])
async def set_output_dir(body: dict):
    """Set the output directory where the agent writes files."""
    path = body.get("path", "").strip()
    if not path:
        return {"error": "path is required"}
    result = workspace.set_output_dir(path)
    if result == "ok":
        return workspace.to_dict()
    return {"error": result}


if __name__ == "__main__":
    agent_os.serve(app="agno_assist:app", port=7777, reload=True)
