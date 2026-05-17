from __future__ import annotations

import argparse
import json

from .agent import LangGraphAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LangGraph prototype agent.")
    parser.add_argument("message", help="User message to send to the agent")
    parser.add_argument("--session-id", default="default", help="Persistent LangGraph thread id")
    args = parser.parse_args()

    agent = LangGraphAgent()
    result = agent.invoke(args.message, session_id=args.session_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

