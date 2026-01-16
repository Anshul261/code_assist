import glob as globlib
import json
import os
import pathlib
import re
import subprocess
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = (
    "https://openrouter.ai/api/v1/messages"
    if OPENROUTER_KEY
    else "https://api.anthropic.com/v1/messages"
)
MODEL = os.environ.get(
    "MODEL",
    "anthropic/claude-sonnet-4" if OPENROUTER_KEY else "claude-sonnet-4-20250514",
)

# ANSI colors
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED = "\033[34m", "\033[36m", "\033[32m", "\033[33m", "\033[31m"

# Working directory for path safety
WORKING_DIR = pathlib.Path.cwd().resolve()


def safe_path(path: str) -> pathlib.Path:
    """Validate path is within working directory to prevent traversal attacks."""
    resolved = (WORKING_DIR / path).resolve()
    try:
        resolved.relative_to(WORKING_DIR)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside working directory")
    return resolved


# --- Tool implementations ---


def read(args):
    path = safe_path(args["path"])
    if not path.exists():
        return f"error: file not found: {args['path']}"
    if path.is_dir():
        return f"error: path is a directory, not a file: {args['path']}"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    offset = args.get("offset", 0)
    limit = args.get("limit", len(lines))
    selected = lines[offset : offset + limit]
    return "".join(f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected))


def write(args):
    path = safe_path(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"], encoding="utf-8")
    return "ok"


def edit(args):
    path = safe_path(args["path"])
    if not path.exists():
        return f"error: file not found: {args['path']}"
    text = path.read_text(encoding="utf-8")
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old_string not found"
    count = text.count(old)
    if not args.get("all") and count > 1:
        return f"error: old_string appears {count} times, must be unique (use all=true)"
    replacement = text.replace(old, new) if args.get("all") else text.replace(old, new, 1)
    path.write_text(replacement, encoding="utf-8")
    return "ok"


def glob(args):
    base = safe_path(args.get("path", "."))
    pattern = args["pat"]
    full_pattern = str(base / pattern)
    files = globlib.glob(full_pattern, recursive=True)
    # Filter to only files within working directory
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


def grep(args):
    try:
        pattern = re.compile(args["pat"])
    except re.error as e:
        return f"error: invalid regex pattern: {e}"

    base = safe_path(args.get("path", "."))
    hits = []
    for filepath in globlib.glob(str(base / "**"), recursive=True):
        # Skip directories and files outside working directory
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


def bash(args):
    cmd = args["cmd"]
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
    try:
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                print(f"  {DIM}| {line.rstrip()}{RESET}", flush=True)
                output_lines.append(line)
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        output_lines.append("\n(timed out after 30s)")
    return "".join(output_lines).strip() or "(empty)"


# --- Tool definitions: (description, schema, function) ---

TOOLS = {
    "read": (
        "Read file with line numbers (file path, not directory)",
        {"path": "string", "offset": "number?", "limit": "number?"},
        read,
    ),
    "write": (
        "Write content to file",
        {"path": "string", "content": "string"},
        write,
    ),
    "edit": (
        "Replace old with new in file (old must be unique unless all=true)",
        {"path": "string", "old": "string", "new": "string", "all": "boolean?"},
        edit,
    ),
    "glob": (
        "Find files by pattern (e.g., **/*.py), sorted by mtime",
        {"pat": "string", "path": "string?"},
        glob,
    ),
    "grep": (
        "Search files for regex pattern",
        {"pat": "string", "path": "string?"},
        grep,
    ),
    "bash": (
        "Run shell command",
        {"cmd": "string"},
        bash,
    ),
}


def run_tool(name, args):
    try:
        return TOOLS[name][2](args)
    except Exception as err:
        return f"error: {err}"


def make_schema():
    result = []
    for name, (description, params, _fn) in TOOLS.items():
        properties = {}
        required = []
        for param_name, param_type in params.items():
            is_optional = param_type.endswith("?")
            base_type = param_type.rstrip("?")
            properties[param_name] = {
                "type": "integer" if base_type == "number" else base_type
            }
            if not is_optional:
                required.append(param_name)
        result.append(
            {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
    return result


def call_api(messages, system_prompt):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(
            {
                "model": MODEL,
                "max_tokens": 8192,
                "system": system_prompt,
                "messages": messages,
                "tools": make_schema(),
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            **(
                {"Authorization": f"Bearer {OPENROUTER_KEY}"}
                if OPENROUTER_KEY
                else {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", "")}
            ),
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=120)
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise Exception(f"API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")


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
        f"{BOLD}nanocode{RESET} | {DIM}{MODEL} ({'OpenRouter' if OPENROUTER_KEY else 'Anthropic'}) | {WORKING_DIR}{RESET}\n"
    )
    messages = []
    system_prompt = f"Concise coding assistant. cwd: {WORKING_DIR}"

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
                messages = []
                print(f"{GREEN}* Cleared conversation{RESET}")
                continue

            messages.append({"role": "user", "content": user_input})

            # agentic loop: keep calling API until no more tool calls
            while True:
                response = call_api(messages, system_prompt)
                content_blocks = response.get("content", [])
                tool_results = []

                for block in content_blocks:
                    if block["type"] == "text":
                        print(f"\n{CYAN}*{RESET} {render_markdown(block['text'])}")

                    if block["type"] == "tool_use":
                        tool_name = block["name"]
                        tool_args = block["input"]
                        arg_preview = str(list(tool_args.values())[0])[:50] if tool_args else ""
                        print(f"\n{GREEN}* {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})")

                        result = run_tool(tool_name, tool_args)
                        result_lines = result.split("\n")
                        preview = result_lines[0][:60]
                        if len(result_lines) > 1:
                            preview += f" ... +{len(result_lines) - 1} lines"
                        elif len(result_lines[0]) > 60:
                            preview += "..."
                        print(f"  {DIM}->  {preview}{RESET}")

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": result,
                            }
                        )

                messages.append({"role": "assistant", "content": content_blocks})

                if not tool_results:
                    break
                messages.append({"role": "user", "content": tool_results})

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
