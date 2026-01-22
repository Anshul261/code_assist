import glob as globlib
import json
import os
import pathlib
import re
import subprocess
from dotenv import load_dotenv

from agno.agent import Agent
from agno.db.sqlite import SqliteDb

# Setup SQLite database
from agno.models.openrouter import OpenRouter
from agno.tools.toolkit import Toolkit
load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.environ.get("MODEL", "claude-sonnet-4-20250514")
db = SqliteDb(db_file="tmp/agents.db")
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED = "\033[34m", "\033[36m", "\033[32m", "\033[33m", "\033[31m"

WORKING_DIR = pathlib.Path.cwd().resolve()


def safe_path(path: str) -> pathlib.Path:
    resolved = (WORKING_DIR / path).resolve()
    try:
        resolved.relative_to(WORKING_DIR)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside working directory")
    return resolved


class CodeAssistToolkit(Toolkit):
    def __init__(self, **kwargs):
        tools = [
            self.read,
            self.write,
            self.edit,
            self.glob,
            self.grep,
            self.bash,
        ]

        super().__init__(name="code_assist_tools", tools=tools, **kwargs)

    def read(self, path: str, offset: int = 0, limit: int = None) -> str:
        """Read file with line numbers (file path, not directory)"""
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
            return "".join(f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected))
        except Exception as err:
            return f"error: {err}"

    def write(self, path: str, content: str) -> str:
        """Write content to file"""
        try:
            safe = safe_path(path)
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return "ok"
        except Exception as err:
            return f"error: {err}"

    def edit(self, path: str, old: str, new: str, all: bool = False) -> str:
        """Replace old with new in file (old must be unique unless all=true)"""
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

    def glob(self, pat: str, path: str = ".") -> str:
        """Find files by pattern (e.g., **/*.py), sorted by mtime"""
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

    def grep(self, pat: str, path: str = ".") -> str:
        """Search files for regex pattern"""
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
                    for line_num, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
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

    def bash(self, cmd: str) -> str:
        """Run shell command"""
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
            proc.wait(timeout=30)
            return "".join(output_lines).strip() or "(empty)"
        except subprocess.TimeoutExpired:
            proc.kill()
            return "(timed out after 30s)"
        except Exception as err:
            return f"error: {err}"


def separator():
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 80
    return f"{DIM}{'─' * min(width, 80)}{RESET}"


def render_markdown(text):
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


def main():
    print(
        f"{BOLD}agnocode{RESET} | {DIM}{MODEL} (OpenRouter via AGNO) | {WORKING_DIR}{RESET}\n"
    )

    toolkit = CodeAssistToolkit()
    agent = Agent(
        model=OpenRouter(id=MODEL, api_key=OPENROUTER_KEY),
        tools=[toolkit],
        markdown=True,
        num_history_sessions=10,
        enable_agentic_memory=True,
        add_session_summary_to_context=True,
        db=db,
    )

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
                agent.clear_history()
                print(f"{GREEN}* Cleared conversation{RESET}")
                continue

            response = agent.run(user_input)

            if response and response.content:
                print(f"\n{CYAN}*{RESET} {render_markdown(response.content)}")

            print()

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Interrupted{RESET}")
            continue
        except EOFError:
            break
        except Exception as err:
            print(f"{RED}* Error: {err}{RESET}")


if __name__ == "__main__":
    main()
