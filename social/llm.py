"""OpenAI wrapper. Single async generate() with one-retry-on-transient-error."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

_ENV_PATH = Path(__file__).parent / "config" / "api_credentials.env"
load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)

_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o") -> None:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise LLMError(
                "OPENAI_API_KEY not set. Add it to social/config/api_credentials.env."
            )
        self._client = AsyncOpenAI(api_key=key)
        self._default_model = default_model

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.85,
        max_tokens: int = 400,
    ) -> str:
        model = model or self._default_model
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                msg = resp.choices[0].message
                if getattr(msg, "refusal", None):
                    return f"[REFUSAL] {msg.refusal}"
                return (msg.content or "").strip()
            except _TRANSIENT as exc:
                last_exc = exc
                if attempt == 1:
                    log.warning("LLM transient error (attempt %d): %s", attempt, exc)
                    await asyncio.sleep(1.5)
                    continue
                raise LLMError(f"LLM transient failure after retry: {exc}") from exc
            except Exception as exc:
                raise LLMError(f"LLM call failed: {exc}") from exc
        raise LLMError(f"unreachable: {last_exc}")


async def _smoke() -> None:
    client = LLMClient()
    out = await client.generate("Reply with the single word: pong")
    print(out)


if __name__ == "__main__":
    asyncio.run(_smoke())
