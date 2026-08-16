#!/usr/bin/env python3
"""Smoke-test Groq chat API using project settings.

Setup:
  1. Create a key at https://console.groq.com/keys
  2. Add to career_intelligence_platform/.env:
       LLM_PROVIDER=groq
       GROQ_API_KEY=gsk_...
  3. Run from backend/:
       python scripts/test_groq.py

Optional:
       python scripts/test_groq.py --stream
       python scripts/test_groq.py --model llama-3.3-70b-versatile
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import AsyncOpenAI

from app.config import settings
from app.services.llm import active_provider, chat_completion, get_chat_model


def _check_env() -> None:
    if not settings.groq_api_key:
        print(
            "GROQ_API_KEY is missing.\n\n"
            "1. Sign up: https://console.groq.com\n"
            "2. Keys -> Create API Key\n"
            "3. Add to career_intelligence_platform/.env:\n"
            "   LLM_PROVIDER=groq\n"
            "   GROQ_API_KEY=gsk_your_key_here\n"
        )
        sys.exit(1)


async def _test_list_models() -> None:
    client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
    )
    models = await client.models.list()
    ids = sorted(m.id for m in models.data)
    print(f"API reachable — {len(ids)} models listed (showing first 8):")
    for mid in ids[:8]:
        print(f"  - {mid}")
    if len(ids) > 8:
        print(f"  ... and {len(ids) - 8} more")


async def _test_chat(model: str, stream: bool) -> None:
    messages = [
        {
            "role": "system",
            "content": "You are a concise assistant for a career intelligence platform.",
        },
        {
            "role": "user",
            "content": (
                "In one short paragraph, explain what a fully-funded PhD fellowship is "
                "and mention one thing applicants should verify on the official site."
            ),
        },
    ]

    print(f"\nChat test — provider={active_provider()} model={model} stream={stream}")
    start = time.perf_counter()

    if stream:
        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
        stream_resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        print("Response (streamed):")
        chunks: list[str] = []
        async for chunk in stream_resp:
            delta = chunk.choices[0].delta.content or ""
            chunks.append(delta)
            print(delta, end="", flush=True)
        print()
        text = "".join(chunks)
    else:
        # Uses app llm service (same path as agents will use).
        if model != get_chat_model():
            client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
            )
            resp = await client.chat.completions.create(model=model, messages=messages)
            text = resp.choices[0].message.content or ""
        else:
            text = await chat_completion(messages, stream=False)
        print("Response:")
        print(text)

    elapsed = time.perf_counter() - start
    print(f"\nOK — {len(text)} chars in {elapsed:.2f}s")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test Groq API connectivity")
    parser.add_argument(
        "--model",
        default=settings.groq_chat_model,
        help=f"Groq model id (default: {settings.groq_chat_model})",
    )
    parser.add_argument("--stream", action="store_true", help="Test streaming completion")
    parser.add_argument("--skip-models", action="store_true", help="Skip models.list() call")
    args = parser.parse_args()

    _check_env()

    print("Groq configuration:")
    print(f"  base_url: {settings.groq_base_url}")
    print(f"  model:    {args.model}")
    print(f"  key:      {settings.groq_api_key[:8]}...{settings.groq_api_key[-4:]}")

    if not args.skip_models:
        await _test_list_models()

    await _test_chat(args.model, args.stream)
    print("\nGroq is ready for agent development.")


if __name__ == "__main__":
    asyncio.run(main())
