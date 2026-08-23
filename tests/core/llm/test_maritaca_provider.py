from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.core.llm.exceptions import LLMProviderError, LLMRateLimitError
from app.core.llm.maritaca_provider import MaritacaProvider
from app.core.llm.schemas import LLMMessage


class _Extraction(BaseModel):
    ready_to_submit: bool
    summary: str


@pytest.fixture
def provider():
    return MaritacaProvider(api_key="test-key", base_url="https://example.test", model="sabia-4")


def _rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(status_code=429, request=httpx.Request("POST", "https://example.test"))
    return openai.RateLimitError("rate limited", response=response, body=None)


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://example.test"))


async def test_complete_returns_llm_response(provider):
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Olá!"))],
        model="sabia-4",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    provider._client.chat.completions.create = AsyncMock(return_value=fake_response)

    result = await provider.complete(
        system="system prompt", messages=[LLMMessage(role="user", content="Oi")]
    )

    assert result.content == "Olá!"
    assert result.model == "sabia-4"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5

    call_kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "sabia-4"
    assert call_kwargs["messages"][0] == {"role": "system", "content": "system prompt"}
    assert call_kwargs["messages"][1] == {"role": "user", "content": "Oi"}


async def test_complete_handles_missing_usage_and_content(provider):
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
        model="sabia-4",
        usage=None,
    )
    provider._client.chat.completions.create = AsyncMock(return_value=fake_response)

    result = await provider.complete(system="system", messages=[])

    assert result.content == ""
    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None


async def test_complete_raises_llm_rate_limit_error(provider):
    provider._client.chat.completions.create = AsyncMock(side_effect=_rate_limit_error())

    with pytest.raises(LLMRateLimitError):
        await provider.complete(system="system", messages=[])


async def test_complete_raises_llm_provider_error(provider):
    provider._client.chat.completions.create = AsyncMock(side_effect=_connection_error())

    with pytest.raises(LLMProviderError):
        await provider.complete(system="system", messages=[])


async def _fake_stream(chunks: list[str | None]):
    for content in chunks:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


async def test_complete_stream_yields_non_empty_deltas(provider):
    provider._client.chat.completions.create = AsyncMock(
        return_value=_fake_stream(["Olá", None, ", ", "", "tudo bem?"])
    )

    deltas = [
        delta
        async for delta in provider.complete_stream(
            system="system prompt", messages=[LLMMessage(role="user", content="Oi")]
        )
    ]

    assert deltas == ["Olá", ", ", "tudo bem?"]

    call_kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "sabia-4"
    assert call_kwargs["stream"] is True
    assert call_kwargs["messages"][0] == {"role": "system", "content": "system prompt"}


async def test_complete_stream_raises_llm_rate_limit_error(provider):
    provider._client.chat.completions.create = AsyncMock(side_effect=_rate_limit_error())

    with pytest.raises(LLMRateLimitError):
        async for _ in provider.complete_stream(system="system", messages=[]):
            pass


async def test_complete_stream_raises_llm_provider_error(provider):
    provider._client.chat.completions.create = AsyncMock(side_effect=_connection_error())

    with pytest.raises(LLMProviderError):
        async for _ in provider.complete_stream(system="system", messages=[]):
            pass


async def test_complete_structured_returns_parsed_schema(provider):
    fake_response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(text='{"ready_to_submit": true, "summary": "resumo"}')]
            )
        ]
    )
    provider._client.responses.create = AsyncMock(return_value=fake_response)

    result = await provider.complete_structured(
        system="system prompt",
        messages=[LLMMessage(role="user", content="Oi")],
        schema=_Extraction,
    )

    assert isinstance(result, _Extraction)
    assert result.ready_to_submit is True
    assert result.summary == "resumo"

    call_kwargs = provider._client.responses.create.call_args.kwargs
    assert call_kwargs["instructions"] == "system prompt"
    assert call_kwargs["input"] == "user: Oi"
    assert call_kwargs["text"]["format"]["name"] == "_Extraction"


async def test_complete_structured_raises_llm_rate_limit_error(provider):
    provider._client.responses.create = AsyncMock(side_effect=_rate_limit_error())

    with pytest.raises(LLMRateLimitError):
        await provider.complete_structured(system="system", messages=[], schema=_Extraction)


async def test_complete_structured_raises_llm_provider_error(provider):
    provider._client.responses.create = AsyncMock(side_effect=_connection_error())

    with pytest.raises(LLMProviderError):
        await provider.complete_structured(system="system", messages=[], schema=_Extraction)
