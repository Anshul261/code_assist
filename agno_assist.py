import glob as globlib
import os
import pathlib
import re
import subprocess

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
WORKSPACE_DIR = WORKING_DIR / "test"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def safe_path(path: str) -> pathlib.Path:
    resolved = (WORKING_DIR / path).resolve()
    try:
        resolved.relative_to(WORKING_DIR)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside working directory")
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
    """Tools for file operations - reading, writing, editing, searching"""

    def __init__(self, **kwargs):
        tools = [self.read, self.write, self.edit, self.glob, self.grep]
        super().__init__(name="file_tools", tools=tools, **kwargs)

    def read(self, path: str = None, offset: int = 0, limit: int = None) -> str:
        """Read a file and return its contents with line numbers.

        Args:
            path: Path to the file to read (REQUIRED). Example: "test/script.js"
            offset: Line number to start reading from (0-indexed). Default: 0
            limit: Maximum number of lines to read. Default: all lines

        Returns:
            File contents with line numbers, or an error message.
        """
        if not path:
            return "error: 'path' parameter is required. Please provide the file path to read. Example: read(path='test/script.js')"
        try:
            safe = safe_path(path)
            if not safe.exists():
                return f"error: file not found: {path}"
            if safe.is_dir():
                return f"error: path is a directory, not a file: {path}"
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
        """Write content to a file, creating parent directories if needed.

        Args:
            path: Path to the file to write (REQUIRED). Example: "test/output.js"
            content: Content to write to the file (REQUIRED)

        Returns:
            "ok" on success, or an error message.
        """
        if not path:
            return "error: 'path' parameter is required. Example: write(path='test/output.js', content='...')"
        if content is None:
            return "error: 'content' parameter is required. Example: write(path='test/output.js', content='...')"
        try:
            safe = safe_path(path)
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return "ok"
        except Exception as err:
            return f"error: {err}"

    def edit(
        self, path: str = None, old: str = None, new: str = None, all: bool = False
    ) -> str:
        """Replace text in a file. The 'old' text must be unique in the file unless all=true.

        Args:
            path: Path to the file to edit (REQUIRED). Example: "test/script.js"
            old: The exact text to find and replace (REQUIRED)
            new: The replacement text (REQUIRED, can be empty string to delete)
            all: If true, replace all occurrences. Default: false (requires unique match)

        Returns:
            "ok" on success, or an error message.
        """
        if not path:
            return "error: 'path' parameter is required. Example: edit(path='file.js', old='old text', new='new text')"
        if old is None:
            return "error: 'old' parameter is required. This is the text to find and replace."
        if new is None:
            return "error: 'new' parameter is required. This is the replacement text."
        try:
            safe = safe_path(path)
            if not safe.exists():
                return f"error: file not found: {path}"
            text = safe.read_text(encoding="utf-8")
            if old not in text:
                return "error: old_string not found"
            count = text.count(old)
            if not all and count > 1:
                return f"error: old_string appears {count} times, must be unique (use all=true)"
            replacement = text.replace(old, new) if all else text.replace(old, new, 1)
            safe.write_text(replacement, encoding="utf-8")
            return "ok"
        except Exception as err:
            return f"error: {err}"

    def glob(self, pat: str = None, path: str = ".") -> str:
        """Find files matching a glob pattern, sorted by modification time (newest first).

        Args:
            pat: Glob pattern to match (REQUIRED). Examples: "**/*.py", "test/*.js", "*.txt"
            path: Directory to search in. Default: current directory

        Returns:
            Newline-separated list of matching file paths, or "none" if no matches.
        """
        if not pat:
            return "error: 'pat' parameter is required. Example: glob(pat='**/*.py') or glob(pat='test/*.js')"
        try:
            base = safe_path(path)
            full_pattern = str(base / pat)
            files = globlib.glob(full_pattern, recursive=True)
            safe_files = []
            for f in files:
                try:
                    pathlib.Path(f).resolve().relative_to(WORKING_DIR)
                    safe_files.append(f)
                except ValueError:
                    continue
            safe_files = sorted(
                safe_files,
                key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0,
                reverse=True,
            )
            return "\n".join(safe_files) or "none"
        except Exception as err:
            return f"error: {err}"

    def grep(self, pat: str = None, path: str = ".") -> str:
        """Search file contents for a regex pattern.

        Args:
            pat: Regular expression pattern to search for (REQUIRED). Example: "function.*export"
            path: File or directory to search in. Default: current directory

        Returns:
            Matching lines in format "filepath:line_num:content", or "none" if no matches.
            Limited to first 50 matches.
        """
        if not pat:
            return "error: 'pat' parameter is required. Example: grep(pat='function') or grep(pat='import.*react')"
        try:
            pattern = re.compile(pat)
        except re.error as e:
            return f"error: invalid regex pattern: {e}"

        try:
            base = safe_path(path)
            hits = []
            for filepath in globlib.glob(str(base / "**"), recursive=True):
                fp = pathlib.Path(filepath)
                if not fp.is_file():
                    continue
                try:
                    fp.resolve().relative_to(WORKING_DIR)
                except ValueError:
                    continue
                try:
                    for line_num, line in enumerate(
                        fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                    ):
                        if pattern.search(line):
                            hits.append(f"{filepath}:{line_num}:{line.rstrip()}")
                            if len(hits) >= 50:
                                break
                    if len(hits) >= 50:
                        break
                except Exception:
                    pass
            return "\n".join(hits) or "none"
        except Exception as err:
            return f"error: {err}"


class BashToolkit(Toolkit):
    """Tools for executing shell commands"""

    def __init__(self, **kwargs):
        tools = [self.bash]
        super().__init__(name="bash_tools", tools=tools, **kwargs)

    def bash(self, cmd: str = None, timeout: int = 120) -> str:
        """Execute a shell command and return its output.

        Args:
            cmd: The shell command to execute (REQUIRED). Example: "ls -la" or "npm install"
            timeout: Maximum seconds to wait for command completion. Default: 120

        Returns:
            The command output (stdout and stderr combined), or an error message.
        """
        if not cmd or not cmd.strip():
            return "error: 'cmd' parameter is required. Please provide the shell command to execute. Example: bash(cmd='ls -la')"
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

CODE_ASSISTANT_INSTRUCTIONS = """You help with coding tasks - reading, writing, editing files and running commands.

## Capabilities
- Read any file in the project
- Write new files or edit existing ones
- Search files by name pattern (glob) or content (grep)
- Run shell commands
- Search the web for information using DuckDuckGo

## Best Practices
- Always read a file before editing it
- Use glob to find files: `**/*.py`, `**/*.js`
- Use grep to search content
- Use DuckDuckGo search when you need up-to-date information or answers from the web
- Explain what you're doing
"""


# =============================================================================
# MODEL FACTORY
# =============================================================================


def get_ollama_models(host: str = None) -> list[dict]:
    """Fetch locally available models from the Ollama API."""
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

db = SqliteDb(
    db_file=DB_PATH,
    session_table="agent_sessions",
)

model = build_model()

compression_manager = CompressionManager(
    model=model,
    compress_tool_results=True,
    compress_tool_results_limit=5,
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
    """List available LLM providers and their status."""
    return {"providers": PROVIDERS}


@app.get("/api/providers/{provider}/models", tags=["Providers"])
async def list_provider_models(provider: str):
    """List models for a given provider."""
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider: {provider}", "models": []}
    info = PROVIDERS[provider]
    if info["status"] != "active":
        return {"error": f"{info['name']} is {info['status']}", "models": []}
    if provider == "ollama":
        models = get_ollama_models()
        return {"models": models}
    return {"models": []}


@app.get("/api/available-models", tags=["Models"])
async def list_models():
    """List available models and the currently active one."""
    current = assistant.model
    current_id = getattr(current, "id", str(current))
    models = get_ollama_models()
    return {
        "models": models,
        "current": current_id,
    }


@app.post("/api/switch-model", tags=["Models"])
async def switch_model(body: dict):
    """Switch the agent's model at runtime."""
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


if __name__ == "__main__":
    agent_os.serve(app="agno_assist:app", port=7777, reload=True)
