#!/usr/bin/env python3
"""Smoke-test LangSmith tracing configuration.

Setup:
  1. Create key at https://smith.langchain.com/settings
  2. Add to career_intelligence_platform/.env:
       LANGSMITH_TRACING=true
       LANGSMITH_API_KEY=lsv2_...
       LANGSMITH_PROJECT=career-intelligence
  3. Run from backend/:
       python scripts/test_langsmith.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.telemetry.langsmith import configure_langsmith, langsmith_enabled
from app.services.llm import active_provider, chat_completion_text as chat_completion, get_chat_model


async def main() -> None:
    configure_langsmith()
    if not langsmith_enabled():
        print(
            "LangSmith tracing is not enabled.\n"
            "Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env\n"
            "See https://smith.langchain.com/"
        )
        sys.exit(1)

    print(f"LangSmith project: {settings.langsmith_project}")
    print(f"Provider: {active_provider()} model: {get_chat_model()}")
    print("Sending test chat_completion (creates a trace with nested LLM span)...")

    reply = await chat_completion(
        [
            {"role": "system", "content": "Reply in one short sentence."},
            {"role": "user", "content": "What is a funded PhD fellowship?"},
        ]
    )
    print(f"Reply: {reply[:200]}")
    print("\nOK — open LangSmith and filter by project:", settings.langsmith_project)


if __name__ == "__main__":
    asyncio.run(main())
