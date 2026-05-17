from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

from .memory import MemoryStore
from .runlog import append_log, run_context, start_run
from .sandbox import Sandbox, sandbox_from_env
from .tools import build_tools

load_dotenv()


SYSTEM_PROMPT = """You are a LangGraph research and document-generation agent.

You run inside a sandbox:
- Uploaded files are readable through list_uploaded_files and read_text_file.
- Generated files must be written under outputs through the document tools or write_markdown.
- Never claim a file exists until a tool reports its path.
- For research, search first, fetch source URLs, then write a concise cited report.
- For research tasks, work iteratively: plan, search multiple queries, fetch primary/relevant sources, compare evidence, write notes, then produce the requested artifact.
- For PPT/Word requests, create the final downloadable file and include its path.
- For polished Word reports, investment briefs, market notes, or research memos, use create_analyst_word_report with English report text.
- Use think before substantive tool work and analyze after major tool results. Keep these entries concise and operational: do not write private chain-of-thought; record only plan, evidence status, next action, and confidence.
- Use memory only for durable preferences, facts, and project decisions.
- Prefer cheap/free tools: DuckDuckGo search, direct URL fetch, python-docx, python-pptx, openpyxl, and the local PPT skill script.
- Do not use emojis unless the user explicitly asks for them.
"""


class LangGraphAgent:
    def __init__(self, sandbox: Sandbox | None = None, model_config: ModelConfig | None = None):
        self.sandbox = sandbox or sandbox_from_env()
        self.model_config = model_config or ModelConfig.from_env()
        self.sandbox.ensure()
        self.memory = MemoryStore(self.sandbox.memory_path)
        self._stack = ExitStack()
        self.checkpointer = self._stack.enter_context(
            SqliteSaver.from_conn_string(str(self.sandbox.db_path))
        )
        self.graph = create_react_agent(
            model=self._build_model(),
            tools=build_tools(self.sandbox, self.memory),
            prompt=SYSTEM_PROMPT,
            checkpointer=self.checkpointer,
        )

    def _build_model(self) -> ChatOpenAI:
        provider = self.model_config.provider
        model = self.model_config.model
        temperature = self.model_config.temperature

        if provider == "openrouter":
            api_key = self.model_config.api_key or os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter")
            if "/" not in model:
                model = "openai/gpt-4o-mini"
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=temperature,
                default_headers={
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:7788"),
                    "X-Title": os.getenv("OPENROUTER_APP_NAME", "Code Assist LangGraph Prototype"),
                },
            )

        api_key = os.getenv("OPENAI_API_KEY")
        if self.model_config.provider == "openai":
            api_key = self.model_config.api_key or api_key
        if not api_key:
            raise RuntimeError("Set OPENAI_API_KEY or OPENROUTER_API_KEY before running the LangGraph agent")
        return ChatOpenAI(model=model, api_key=api_key, temperature=temperature)

    def invoke(self, message: str, session_id: str = "default") -> dict:
        start_run(session_id, message)
        with run_context(session_id):
            append_log("model", "Agent started", f"Model: {self.model_config.provider} · {self.model_config.model}")
            result = self.graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": session_id}},
            )
        final = result["messages"][-1]
        append_log("run", "Run finished", "Final response returned.", session_id=session_id)
        return {
            "session_id": session_id,
            "response": final.content,
            "outputs": self.sandbox.list_outputs(),
        }


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    api_key: str = ""
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "ModelConfig":
        provider = os.getenv("LANGGRAPH_MODEL_PROVIDER", "").lower()
        if not provider:
            provider = "openrouter" if os.getenv("OPENROUTER_API_KEY") else "openai"
        model = os.getenv("LANGGRAPH_MODEL") or os.getenv("MODEL")
        if not model:
            model = "openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini"
        if provider == "openrouter" and "/" not in model:
            model = "openai/gpt-4o-mini"
        api_key = os.getenv("OPENROUTER_API_KEY") if provider == "openrouter" else os.getenv("OPENAI_API_KEY")
        temperature = float(os.getenv("LANGGRAPH_TEMPERATURE", "0.2"))
        return cls(provider=provider, model=model, api_key=api_key or "", temperature=temperature)
