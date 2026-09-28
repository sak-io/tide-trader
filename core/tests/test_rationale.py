from datetime import UTC, datetime
from types import SimpleNamespace

from app.engine.rationale import AnthropicMessagesClient, RationaleGenerator
from app.models.domain import IndicatorSnapshot, Signal, SignalDirection, SignalSource
from tests.fakes import FakeAnthropicClient


def _signal() -> Signal:
    return Signal(
        symbol="AAPL",
        direction=SignalDirection.bullish,
        price=190.0,
        score=85.0,
        indicators=IndicatorSnapshot(sma_fast=105.0, sma_slow=102.0, rsi14=60.0, volume_ratio=2.0),
        triggered_rules=["golden_cross_sma20_sma50"],
        sources=[SignalSource.watchlist],
        generated_at=datetime(2026, 9, 28, tzinfo=UTC),
    )


async def test_generate_returns_none_when_no_client_is_configured():
    generator = RationaleGenerator(client=None, model="claude-opus-5")
    assert await generator.generate(_signal()) is None


async def test_generate_returns_text_on_success():
    client = FakeAnthropicClient(response_text="AAPL just posted a golden cross with strong volume.")
    generator = RationaleGenerator(client=client, model="claude-opus-5")

    result = await generator.generate(_signal())

    assert result == "AAPL just posted a golden cross with strong volume."
    assert client.calls[0]["model"] == "claude-opus-5"
    assert client.calls[0]["messages"][0]["role"] == "user"
    assert "AAPL" in client.calls[0]["messages"][0]["content"]


async def test_generate_returns_none_on_any_client_exception():
    client = FakeAnthropicClient(should_raise=True)
    generator = RationaleGenerator(client=client, model="claude-opus-5")

    assert await generator.generate(_signal()) is None


async def test_generate_returns_none_when_the_response_has_no_text_block():
    class _NoTextClient:
        async def create_message(self, *, model, max_tokens, messages):
            return SimpleNamespace(content=[SimpleNamespace(type="other")])

    generator = RationaleGenerator(client=_NoTextClient(), model="claude-opus-5")
    assert await generator.generate(_signal()) is None


async def test_anthropic_messages_client_delegates_to_the_sdk(monkeypatch):
    calls = []

    class _FakeMessages:
        async def create(self, *, model, max_tokens, messages):
            calls.append((model, max_tokens, messages))
            return "raw-response"

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            self.api_key = api_key
            self.messages = _FakeMessages()

    import app.engine.rationale as rationale_module

    monkeypatch.setattr(rationale_module.anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)

    client = rationale_module.AnthropicMessagesClient(api_key="fake-key")
    result = await client.create_message(
        model="claude-opus-5", max_tokens=10, messages=[{"role": "user", "content": "hi"}]
    )

    assert result == "raw-response"
    assert calls == [("claude-opus-5", 10, [{"role": "user", "content": "hi"}])]
    assert isinstance(client, AnthropicMessagesClient)
