"""LLM-generated plain-English rationale for an already-decided signal.

The screener (see `app.engine.screener`) alone decides direction/score - this module
only asks Claude to explain a decision that's already been made. It never feeds
back into the decision, and it's deliberately failure-tolerant: any problem talking
to Anthropic (no API key configured, network error, malformed response, ...) simply
results in `generate()` returning None, so a suggestion is still created/shown
without a rationale rather than being dropped.
"""

import logging
from typing import Any, Protocol

import anthropic

from app.models.domain import Signal

logger = logging.getLogger(__name__)

_MAX_TOKENS = 300


class AnthropicClientProtocol(Protocol):
    """The subset of an Anthropic Messages client this generator depends on."""

    async def create_message(
        self, *, model: str, max_tokens: int, messages: list[dict[str, Any]]
    ) -> Any: ...


class AnthropicMessagesClient:
    """Thin wrapper around anthropic.AsyncAnthropic's `.messages.create(...)`.

    Satisfies AnthropicClientProtocol so RationaleGenerator never depends on the
    `anthropic` package's own types directly.
    """

    def __init__(self, api_key: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def create_message(self, *, model: str, max_tokens: int, messages: list[dict[str, Any]]) -> Any:
        return await self._client.messages.create(model=model, max_tokens=max_tokens, messages=messages)


def _build_prompt(signal: Signal) -> str:
    indicators = signal.indicators
    return "\n".join(
        [
            f"A deterministic technical screener flagged {signal.symbol} as a {signal.direction.value} "
            f"signal (composite score {signal.score:.0f}/100) at a price of ${signal.price:.2f}.",
            f"Indicators: SMA20={indicators.sma_fast:.2f}, SMA50={indicators.sma_slow:.2f}, "
            f"RSI14={indicators.rsi14:.1f}, volume ratio={indicators.volume_ratio:.2f}.",
            f"Triggered rules: {', '.join(signal.triggered_rules)}.",
            "Write a brief (2-3 sentence) plain-English rationale a retail trader could read at a "
            "glance, explaining what the indicators show. Do not recommend an order size or specific "
            "action, and do not mention options - this is informational only.",
        ]
    )


class RationaleGenerator:
    """Asks Claude to explain an already-decided Signal. Never raises."""

    def __init__(self, client: AnthropicClientProtocol | None, model: str):
        self._client = client
        self._model = model

    async def generate(self, signal: Signal) -> str | None:
        if self._client is None:
            return None

        try:
            response = await self._client.create_message(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": _build_prompt(signal)}],
            )
            for block in getattr(response, "content", []):
                if getattr(block, "type", None) == "text":
                    return block.text
            return None
        except Exception:
            logger.exception("Rationale generation failed for %s; continuing without one.", signal.symbol)
            return None
