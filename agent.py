import argparse
import glob as globlib
import os
import pathlib
import re
import subprocess

from agno.agent import Agent
from agno.compression.manager import CompressionManager
from agno.models.ollama import Ollama
from agno.tools.toolkit import Toolkit
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST")
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED, MAGENTA = (
    "\033[34m",
    "\033[36m",
    "\033[32m",
    "\033[33m",
    "\033[31m",
    "\033[35m",
)

WORKING_DIR = pathlib.Path.cwd().resolve()
WORKSPACE_DIR = WORKING_DIR / "test"


def safe_path(path: str) -> pathlib.Path:
    resolved = (WORKING_DIR / path).resolve()
    try:
        resolved.relative_to(WORKING_DIR)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside working directory")
    return resolved


# =============================================================================
# TOOLKITS - Specialized tools for each agent
# =============================================================================


class FileToolkit(Toolkit):
    """Tools for file operations - reading, writing, editing, searching"""

class FileToolkit(Toolkit):
    """Tools for file operations - reading, writing, editing, searching"""

    def __init__(self, **kwargs):
        tools = [self.read, self.write, self.edit, self.glob, self.grep]
        super().__init__(name="file_tools", tools=tools, **kwargs)

    def read(self, path: str | None = None, offset: int = 0, limit: int | None = None) -> str:
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

    def write(self, path: str | None = None, content: str | None = None) -> str:
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
        self, path: str | None = None, old: str | None = None, new: str | None = None, all: bool = False
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

    def glob(self, pat: str | None = None, path: str = ".") -> str:
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

    def grep(self, pat: str | None = None, path: str = ".") -> str:
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

    def bash(self, cmd: str | None = None, timeout: int = 120) -> str:
        """Execute a shell command and return its output.

        Args:
            cmd: The shell command to execute (REQUIRED). Example: "ls -la" or "npm install"
            timeout: Maximum seconds to wait for command completion. Default: 120

        Returns:
            The command output (stdout and stderr combined), or an error message.
        """
        # Validate required parameter
        if not cmd or not cmd.strip():
            return "error: 'cmd' parameter is required. Please provide the shell command to execute. Example: bash(cmd='ls -la')"
        try:
            print(f"  {DIM}$ {cmd}{RESET}")
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
                    print(f"  {DIM}| {line.rstrip()}{RESET}", flush=True)
                    output_lines.append(line)
            proc.wait(timeout=timeout)
            return "".join(output_lines).strip() or "(empty)"
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"(timed out after {timeout}s)"
        except Exception as err:
            return f"error: {err}"


# =============================================================================
# AGENT INSTRUCTIONS
# =============================================================================

CODE_ASSISTANT_INSTRUCTIONS = """You help with coding tasks - reading, writing, editing files and running commands.

## Capabilities
- Read any file in the project
- Write new files or edit existing ones
- Search files by name pattern (glob) or content (grep)
- Run shell commands

## Best Practices
- Always read a file before editing it
- Use glob to find files: `**/*.py`, `**/*.js`
- Use grep to search content
- Explain what you're doing
"""


# =============================================================================
# MAIN
# =============================================================================


def separator():
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80
    return f"{DIM}{'─' * min(width, 80)}{RESET}"


def render_markdown(text):
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


def resolve_runtime_config():
    parser = argparse.ArgumentParser(
        description="Run AGNO agent with Ollama"
    )
    parser.add_argument("--model", help="Ollama model name (default: llama3.1)")
    parser.add_argument(
        "--ollama-host", help="Ollama host URL, e.g. http://localhost:11434"
    )
    args = parser.parse_args()

    model = args.model or os.getenv("MODEL", "llama3.1")
    ollama_host = args.ollama_host or OLLAMA_HOST
    return model, ollama_host


def build_model(model_id: str, ollama_host: str | None):
    kwargs = {"id": model_id}
    if ollama_host:
        kwargs["host"] = ollama_host
    return Ollama(**kwargs)


def main():
    model_id, ollama_host = resolve_runtime_config()
    print(
        f"{BOLD}local code assistant{RESET} | {DIM}{model_id} (Ollama) | {WORKING_DIR}{RESET}\n"
    )

    # Ensure workspace directory exists
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Shared model
    model = build_model(
        model_id=model_id, ollama_host=ollama_host
    )

    # Context compression manager
    compression_manager = CompressionManager(
        model=model,  # Use same model for compression
        compress_tool_results=True,
        compress_tool_results_limit=5,
    )

    assistant = Agent(
        name="Code Assistant",
        role="Handles file operations, code reading/writing/editing, and shell commands",
        model=model,
        tools=[FileToolkit(), BashToolkit()],
        instructions=CODE_ASSISTANT_INSTRUCTIONS,
        markdown=True,
        compress_tool_results=True,
        compression_manager=compression_manager,
        add_history_to_context=True,
        num_history_runs=10,
        read_chat_history=True,
    )
    print(f"{DIM}Single-agent mode: Code Assistant{RESET}\n")

    while True:
        try:
            print(separator())
            user_input = input(f"{BOLD}{BLUE}>{RESET} ").strip()
            print(separator())
            if not user_input:
                continue
            if user_input in ("/q", "exit"):
                break
            if user_input == "/c":
                assistant = Agent(
                    name="Code Assistant",
                    role="Handles file operations, code reading/writing/editing, and shell commands",
                    model=model,
                    tools=[FileToolkit(), BashToolkit()],
                    instructions=CODE_ASSISTANT_INSTRUCTIONS,
                    markdown=True,
                    compress_tool_results=True,
                    compression_manager=compression_manager,
                    add_history_to_context=True,
                    num_history_runs=10,
                    read_chat_history=True,
                )
                print(f"{GREEN}* Cleared conversation{RESET}")
                continue

            print(f"{DIM}Running agent...{RESET}")
            response = assistant.run(user_input)
            print(f"{DIM}Response type: {type(response)}, content length: {len(response.content) if response and response.content else 0}{RESET}")
            if response and response.content:
                print(render_markdown(response.content))

            print()

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Interrupted{RESET}")
            continue
        except EOFError:
            break
        except Exception as err:
            import traceback

            print(f"{RED}* Error: {err}{RESET}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
