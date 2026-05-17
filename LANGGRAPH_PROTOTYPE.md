# LangGraph Prototype

This is a separate LangGraph path for local testing. It does not replace the existing Agno app.

## What It Includes

- LangGraph `create_react_agent` with SQLite checkpointed sessions.
- OpenAI or OpenRouter model support.
- Sandboxed uploads under `lg_workspace/uploads`.
- Sandboxed generated artifacts under `lg_workspace/outputs`.
- Download endpoint for generated artifacts.
- DuckDuckGo search through `ddgs`.
- URL fetch through `httpx`.
- File understanding for txt/md/pdf/docx/pptx/xlsx/csv.
- Document generation for Markdown, Word, PowerPoint, and Excel.
- Optional PPT generation through the existing local `skills/ppt` script.
- Simple long-term memory in SQLite.

## Cost Notes

- Cheapest/free external tools: DuckDuckGo search via `ddgs`, direct URL fetch, local Python document libraries.
- Cheap model path: OpenRouter with low-cost tool-calling models.
- Reliable model path: direct OpenAI key with `gpt-4o-mini` or equivalent small tool-capable model.
- Storage path for local testing: SQLite and local files. No Railway deployment yet.

## Run Locally

Set either OpenAI or OpenRouter credentials:

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

Start the local API:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn langgraph_assist.app:app --reload --port 7789
```

Open:

```text
http://localhost:7789/docs
```

## Test Upload And Download

Upload a file:

```bash
curl -F "file=@README.md" http://localhost:7789/upload
```

Ask the agent to use it:

```bash
curl -X POST http://localhost:7789/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","message":"Read README.md and create a 5-slide PPT summary. Return the downloadable path."}'
```

List outputs:

```bash
curl http://localhost:7789/outputs
```

Download an artifact:

```bash
curl -L "http://localhost:7789/download/presentation.pptx" -o presentation.pptx
```

## CLI Test

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m langgraph_assist.cli \
  "Search for recent LangGraph agent patterns, fetch two sources, and write a markdown report."
```
