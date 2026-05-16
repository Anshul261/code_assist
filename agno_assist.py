import glob as globlib
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass, field

import httpx
from fastapi import Response
from fastapi.responses import FileResponse
from agno.agent import Agent
from agno.compression.manager import CompressionManager
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama
from agno.skills import LocalSkills, Skills
from agno.team import Team, TeamMode


def _get_openrouter():
    """Lazy import to avoid requiring openai when only using Ollama."""
    from agno.models.openrouter import OpenRouter
    return OpenRouter
from agno.os import AgentOS
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.toolkit import Toolkit
from dotenv import load_dotenv

from tools.visualization_tools import VisualizationTools

load_dotenv()

# Anchor cwd to the script's directory so paths are stable regardless of launch dir
os.chdir(pathlib.Path(__file__).parent)

WORKING_DIR = pathlib.Path.cwd().resolve()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:7777")
SKILLS_DIR = WORKING_DIR / "skills"


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
    "openrouter": {
        "name": "OpenRouter",
        "status": "active",
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


class WorkProductToolkit(Toolkit):
    """Higher-level tools for common work products."""

    def __init__(self, **kwargs):
        super().__init__(
            name="work_product_tools",
            tools=[self.create_excel_analysis_ppt, self.create_ppt_from_markdown],
            **kwargs,
        )

    def create_ppt_from_markdown(
        self,
        markdown_content: str,
        output_name: str = "presentation",
    ) -> str:
        """Create a PPTX deck from markdown slide content.

        Use this when the assistant already has a slide outline or can create one from research notes.
        The first markdown H1 becomes the deck title; each H2 becomes a slide.

        Args:
            markdown_content: Slide markdown. Use one H1 title and H2 headings for slides.
            output_name: Base filename for generated scratch markdown and deck, without extension.

        Returns:
            JSON string with the scratch outline path, deck path, slide count, and status.
        """
        try:
            import json

            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", output_name).strip("-").lower()
            if not safe_name:
                safe_name = "presentation"

            outline_path = _resolve_write(f"scratch/{safe_name}-slide-outline.md")
            deck_path = _resolve_write(f"decks/{safe_name}.pptx")
            outline_path.parent.mkdir(parents=True, exist_ok=True)
            deck_path.parent.mkdir(parents=True, exist_ok=True)
            outline_path.write_text(markdown_content.rstrip() + "\n", encoding="utf-8")

            ppt_cmd = [
                "node",
                str(WORKING_DIR / "skills" / "ppt" / "scripts" / "create_pptx.js"),
                "--spec",
                str(outline_path),
                "--output",
                str(deck_path),
            ]
            ppt_proc = subprocess.run(
                ppt_cmd,
                cwd=WORKING_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
            if ppt_proc.returncode != 0:
                return json.dumps(
                    {
                        "status": "error",
                        "step": "create_pptx",
                        "outline": str(outline_path),
                        "output": ppt_proc.stdout[-4000:],
                    }
                )
            deck_result = json.loads(ppt_proc.stdout)
            return json.dumps(
                {
                    "status": "success",
                    "outline": str(outline_path),
                    "deck": deck_result["output"],
                    "slides": deck_result["slides"],
                },
                indent=2,
            )
        except Exception as err:
            return json.dumps({"status": "error", "error": str(err)})

    def create_excel_analysis_ppt(
        self,
        workbook_path: str,
        output_name: str = "excel-analysis",
    ) -> str:
        """Analyze an Excel workbook and create scratch notes, a report, chart PNGs, and a PPTX deck.

        Args:
            workbook_path: Path to the Excel workbook to analyze.
            output_name: Base filename for the final deck, without extension.

        Returns:
            JSON string with generated artifact paths, or an error.
        """
        try:
            import json

            workbook = _resolve_read(workbook_path)
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", output_name).strip("-").lower()
            if not safe_name:
                safe_name = "excel-analysis"

            profile_cmd = [
                str(WORKING_DIR / ".venv" / "bin" / "python"),
                str(WORKING_DIR / "skills" / "excel" / "scripts" / "profile_excel.py"),
                str(workbook),
                "--output-dir",
                str(workspace.output_dir),
            ]
            profile_proc = subprocess.run(
                profile_cmd,
                cwd=WORKING_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
            if profile_proc.returncode != 0:
                return json.dumps(
                    {
                        "status": "error",
                        "step": "profile_excel",
                        "output": profile_proc.stdout[-4000:],
                    }
                )
            profile_result = json.loads(profile_proc.stdout)
            report_md = pathlib.Path(profile_result["report_md"])
            deck_path = _resolve_write(f"decks/{safe_name}.pptx")
            deck_path.parent.mkdir(parents=True, exist_ok=True)

            ppt_cmd = [
                "node",
                str(WORKING_DIR / "skills" / "ppt" / "scripts" / "create_pptx.js"),
                "--spec",
                str(report_md),
                "--output",
                str(deck_path),
            ]
            ppt_proc = subprocess.run(
                ppt_cmd,
                cwd=WORKING_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
            if ppt_proc.returncode != 0:
                return json.dumps(
                    {
                        "status": "error",
                        "step": "create_pptx",
                        "output": ppt_proc.stdout[-4000:],
                        "profile": profile_result,
                    }
                )
            deck_result = json.loads(ppt_proc.stdout)
            return json.dumps(
                {
                    "status": "success",
                    "workbook": str(workbook),
                    "profile_md": profile_result["profile_md"],
                    "profile_json": profile_result["profile_json"],
                    "report_md": profile_result["report_md"],
                    "charts": profile_result["charts"],
                    "deck": deck_result["output"],
                    "slides": deck_result["slides"],
                },
                indent=2,
            )
        except Exception as err:
            return json.dumps({"status": "error", "error": str(err)})


# =============================================================================
# INSTRUCTIONS
# =============================================================================

CODE_ASSISTANT_INSTRUCTIONS = """You are a helpful AI assistant.

## How to handle every request — work until done

When the user asks you to do something, you MUST follow these steps in order:

1. **Briefly plan, then immediately act** — for non-trivial work, start with a short plan and then call the needed tools in the same run.
   A response that only says "I will do X" or "Let me do X" without calling tools is a failed response.
   Format the plan clearly:
   ```
   ## Plan
   1. Step one...
   2. Step two...
   3. Step three...
   ```

2. **Then execute** — immediately after writing the plan, call the appropriate tools to do the work. Do NOT ask the user for permission first.

3. **Self-check before stopping** — before the final answer, verify that every requested deliverable exists or was actually completed. If not, keep using tools.

4. **Summarize** — when done, briefly say what was accomplished and include artifact paths when files were created.

## Completion rules
- Do not stop after planning.
- Do not stop after saying "I will write", "I will search", "let me continue", or "let me create".
- If the task asks for research, reports, PPTs, files, charts, or code changes, you must use tools and continue until the requested artifact or result exists.
- If a tool fails, try a narrower query, another available tool, or create a scratch note explaining the failure and continue with the best available evidence.
- For long tasks, write intermediate notes to `scratch/*.md` so work survives context limits.
- Final answers must include concrete results, not just intentions.

## Tools
- ls(path) — list files in a directory
- glob(pat) — find files matching a pattern (e.g. "**/*.md")
- grep(pat) — search file contents for a pattern
- read(path) — read a file (supports offset and limit)
- write(path, content) — write a file to the output directory
- edit(path, old, new) — replace text in a file
- bash(cmd) — run a shell command
- duckduckgo_search(query) — search the web
- visualization tools — create chart PNGs and save chart images
- skill tools — load specialized Excel and PPT instructions/scripts when a task matches a skill
- create_excel_analysis_ppt(workbook_path, output_name) — one-call Excel analysis to report/charts/PPT
- create_ppt_from_markdown(markdown_content, output_name) — one-call markdown outline to PPTX

## Rules
- Always show your plan before executing — the user expects to see it.
- Be specific in your plan — name the exact files and tools you will use.
- If the task is simple (e.g. "read this file"), still show a brief plan.
- For Excel, data analysis, charts, reports, and presentation work, load and follow the relevant skill.
- Persist work artifacts under the output directory: scratch/*.md for notes and plans, reports/*.md for final reports, assets/*.png for charts/images, and decks/*.pptx for presentations.
- Do not build a final PPT directly from raw data. Create a scratch outline or report first, generate assets, then create and verify the deck.
- If the user asks to analyze an Excel file and create a PowerPoint, prefer create_excel_analysis_ppt unless the user asks for custom manual analysis steps.
- If the user asks to turn research or notes into a PPT, create a slide outline and then prefer create_ppt_from_markdown so the deck is generated in the same run.
"""


# =============================================================================
# MODEL FACTORY
# =============================================================================


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_POPULAR_MODELS = [
    {"id": "deepseek/deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "openrouter"},
    {"id": "deepseek/deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "openrouter"},
    {"id": "qwen/qwen3.6-27b", "name": "Qwen 3.6 27B", "provider": "openrouter"},
    {"id": "openai/gpt-oss-120b", "name": "Open AI OSS 120B", "provider": "openrouter"},
    {"id": "z-ai/glm-5.1", "name": "GLM 5.1", "provider": "openrouter"},
    {"id": "moonshotai/kimi-k2.6", "name": "Kimi K2.6", "provider": "openrouter"},
    {"id": "deepseek/deepseek-v3", "name": "DeepSeek V3", "provider": "openrouter"},
    {"id": "nvidia/nemotron-3-super-120b-a12b", "name": "Nemotron 120B", "provider": "openrouter"},
]


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


def get_openrouter_models() -> list[dict]:
    if not OPENROUTER_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            {"id": m["id"], "name": m.get("name", m["id"]), "provider": "openrouter"}
            for m in data[:50]
        ]
    except Exception:
        return OPENROUTER_POPULAR_MODELS


def build_model(provider: str = "ollama", model_id: str = None, host: str = None, api_key: str = None):
    if provider == "openrouter":
        model_id = model_id or "openai/gpt-4o-mini"
        kwargs = {"id": model_id}
        key = api_key or OPENROUTER_API_KEY
        if key:
            kwargs["api_key"] = key
        return _get_openrouter()(**kwargs)

    model_id = model_id or os.getenv("MODEL", "qwen3.5:9b")
    kwargs = {"id": model_id}
    host = host or OLLAMA_HOST
    if host:
        kwargs["host"] = host
    return Ollama(**kwargs)


# =============================================================================
# AGENT OS
# =============================================================================

DEFAULT_PROVIDER = os.getenv("PROVIDER", "ollama")
current_provider = DEFAULT_PROVIDER

DB_PATH = str(WORKING_DIR / "agent_os.db")

db = SqliteDb(db_file=DB_PATH, session_table="agent_sessions")
model = build_model(provider=current_provider)
compression_manager = CompressionManager(
    model=model,
    compress_tool_results=False,
    compress_tool_results_limit=None,
)
visualization_tools = VisualizationTools(
    db_url=f"sqlite:///{DB_PATH}",
    base_url=AGENT_BASE_URL,
    output_dir=workspace.output_dir,
)
skills = Skills(loaders=[LocalSkills(str(SKILLS_DIR))])

assistant = Agent(
    name="Assistant",
    model=model,
    db=db,
    tools=[
        FileToolkit(),
        BashToolkit(),
        WorkProductToolkit(),
        DuckDuckGoTools(enable_search=True, enable_news=True),
        visualization_tools,
    ],
    skills=skills,
    instructions=CODE_ASSISTANT_INSTRUCTIONS,
    markdown=True,
    compress_tool_results=False,
    compression_manager=compression_manager,
    add_history_to_context=True,
    num_history_runs=3,
    max_tool_calls_from_history=0,
    read_chat_history=False,
    tool_call_limit=40,
    expected_output="A completed answer with concrete results and artifact paths when files are created. Never return only a plan.",
    debug_mode=True,
    telemetry=False,
)

data_analyst = Agent(
    name="Data Analyst",
    role="Profiles Excel workbooks deeply, creates durable analysis reports, and produces chart assets.",
    model=model,
    db=db,
    tools=[
        FileToolkit(),
        WorkProductToolkit(),
        visualization_tools,
    ],
    skills=skills,
    instructions=[
        "Use the Excel skill for workbook analysis.",
        "For Excel-to-PPT requests, call create_excel_analysis_ppt(workbook_path, output_name) first so the full report, chart, and deck pipeline completes in one tool call.",
        "Use an absolute workbook path when the user provides one, and return the tool JSON result with artifact paths.",
        "Do not run the Excel skill script directly for Excel-to-PPT work unless create_excel_analysis_ppt is unavailable or fails.",
        "Do not stop after one chart if the task asks for a work product; produce a complete report and multiple relevant visuals.",
        "Your final response must not be empty. Return artifact paths and concise quality notes.",
    ],
    markdown=True,
    compress_tool_results=False,
    compression_manager=compression_manager,
    tool_call_limit=30,
    expected_output="Concrete artifact paths, findings, and quality notes. Never return an empty or plan-only result.",
    telemetry=False,
)

presentation_builder = Agent(
    name="Presentation Builder",
    role="Builds PowerPoint decks from reports, outlines, and chart assets.",
    model=model,
    db=db,
    tools=[
        FileToolkit(),
        WorkProductToolkit(),
    ],
    skills=skills,
    instructions=[
        "Use the PPT skill for any deck or slide request.",
        "Build decks only after a report or outline exists.",
        "When you have or can produce a slide outline, prefer create_ppt_from_markdown so deck creation completes in one tool call.",
        "Stay inside the assigned workspace. Use glob/read for discovery and do not perform broad filesystem searches.",
        "Verify the final .pptx path exists and report the slide count when available.",
        "Your final response must not be empty. Return the final deck path and any source report/chart paths used.",
    ],
    markdown=True,
    compress_tool_results=False,
    compression_manager=compression_manager,
    tool_call_limit=30,
    expected_output="The final deck path, slide count when available, and source report/chart paths. Never return an empty or plan-only result.",
    telemetry=False,
)

quality_reviewer = Agent(
    name="Quality Reviewer",
    role="Reviews generated reports and decks for completeness, missing artifacts, and shallow findings.",
    model=model,
    db=db,
    tools=[FileToolkit(), BashToolkit()],
    instructions=[
        "Check whether the report has concrete values, enough findings, multiple relevant charts, and a valid PPTX artifact.",
        "Flag placeholder text, missing charts, and shallow analysis.",
        "Stay inside the assigned workspace. Do not perform broad filesystem searches.",
        "Keep feedback actionable and grounded in generated files.",
        "Your final response must not be empty.",
    ],
    markdown=True,
    compress_tool_results=False,
    compression_manager=compression_manager,
    tool_call_limit=25,
    expected_output="A grounded quality review with pass/fail status and concrete file paths inspected. Never return an empty result.",
    telemetry=False,
)

work_product_team = Team(
    name="Work Product Team",
    role="Long-running team for deep spreadsheet analysis, reports, charts, and PowerPoint decks.",
    mode=TeamMode.tasks,
    max_iterations=8,
    model=model,
    db=db,
    members=[data_analyst, presentation_builder, quality_reviewer],
    instructions=[
        "Run as a task loop until the work product is complete, not after the first chart or first finding.",
        "For Excel-to-PPT requests, create one primary task for Data Analyst to call create_excel_analysis_ppt with the workbook path and output name. Do not split profile, report, charts, and deck into separate dependent tasks unless the one-call pipeline fails.",
        "Use Presentation Builder only after report/chart artifacts exist, unless Data Analyst already produced the deck.",
        "Use Quality Reviewer to inspect the generated report and deck before the final response.",
        "Do not synthesize or invent artifact paths. If a member result is empty, retry once with explicit instructions to call the concrete tool and return the tool output.",
        "Keep all file discovery inside the assigned workspace. Do not use broad searches from filesystem root.",
        "Success means there is a concrete report, several relevant chart assets when the data supports them, a valid PPTX deck, and a final response with artifact paths.",
    ],
    expected_output="A completed work-product summary with report, chart, and PPTX artifact paths plus a quality review.",
    markdown=True,
    show_members_responses=True,
    store_member_responses=True,
    debug_mode=True,
    telemetry=False,
)

agent_os = AgentOS(
    name="Code Assist",
    db=db,
    agents=[assistant],
    teams=[work_product_team],
    cors_allowed_origins=["http://localhost:3000"],
)

app = agent_os.get_app()


# =============================================================================
# CUSTOM ENDPOINTS
# =============================================================================


@app.get("/api/providers", tags=["Providers"])
async def list_providers():
    return {"providers": PROVIDERS}


@app.get("/api/charts/{chart_id}", tags=["Charts"])
async def get_chart(chart_id: str):
    png_bytes = visualization_tools.get_chart_bytes(chart_id)
    if png_bytes is None:
        return Response(status_code=404, content=b"chart not found")
    return Response(content=png_bytes, media_type="image/png")


@app.get("/api/artifacts", tags=["Artifacts"])
async def get_artifact(path: str):
    """Serve files generated under the configured output directory."""
    try:
        artifact_path = pathlib.Path(path).resolve()
        artifact_path.relative_to(workspace.output_dir.resolve())
    except Exception:
        return Response(status_code=403, content=b"artifact path is outside output directory")
    if not artifact_path.exists() or not artifact_path.is_file():
        return Response(status_code=404, content=b"artifact not found")
    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        content_disposition_type="inline",
    )


@app.get("/api/providers/{provider}/models", tags=["Providers"])
async def list_provider_models(provider: str):
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider: {provider}", "models": []}
    info = PROVIDERS[provider]
    if info["status"] != "active":
        return {"error": f"{info['name']} is {info['status']}", "models": []}
    if provider == "ollama":
        return {"models": get_ollama_models()}
    if provider == "openrouter":
        return {"models": get_openrouter_models()}
    return {"models": []}


@app.get("/api/provider-config", tags=["Providers"])
async def get_provider_config():
    """Return current provider, model, and whether API keys are configured."""
    current_id = getattr(assistant.model, "id", str(assistant.model))
    return {
        "provider": current_provider,
        "model": current_id,
        "openrouter_api_key_set": bool(OPENROUTER_API_KEY),
        "ollama_host": OLLAMA_HOST,
    }


@app.post("/api/provider-config/api-key", tags=["Providers"])
async def update_api_key(body: dict):
    """Update the API key for a provider (currently only OpenRouter)."""
    global OPENROUTER_API_KEY
    provider = body.get("provider", "")
    api_key = body.get("api_key", "").strip()
    if provider == "openrouter":
        OPENROUTER_API_KEY = api_key
        # If currently using OpenRouter, rebuild the model with the new key
        if current_provider == "openrouter":
            new_model = build_model(provider="openrouter", model_id=getattr(assistant.model, "id", None))
            assistant.model = new_model
            compression_manager.model = new_model
        return {"status": "ok", "provider": provider, "api_key_set": bool(api_key)}
    return {"error": f"Unknown provider: {provider}"}


@app.get("/api/available-models", tags=["Models"])
async def list_models():
    current_id = getattr(assistant.model, "id", str(assistant.model))
    if current_provider == "openrouter":
        return {"models": get_openrouter_models(), "current": current_id, "provider": current_provider}
    return {"models": get_ollama_models(), "current": current_id, "provider": current_provider}


@app.post("/api/switch-model", tags=["Models"])
async def switch_model(body: dict):
    global current_provider
    model_id = body.get("model_id")
    provider = body.get("provider", "ollama")
    if not model_id:
        return {"error": "model_id is required"}
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider: {provider}"}
    try:
        current_provider = provider
        new_model = build_model(provider=provider, model_id=model_id)
        assistant.model = new_model
        data_analyst.model = new_model
        presentation_builder.model = new_model
        quality_reviewer.model = new_model
        work_product_team.model = new_model
        compression_manager.model = new_model
        return {"status": "ok", "model": model_id, "provider": provider}
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
    visualization_tools.output_dir = workspace.output_dir
    if result == "ok":
        return workspace.to_dict()
    return {"error": result}


if __name__ == "__main__":
    agent_os.serve(app="agno_assist:app", port=7777, reload=True)
