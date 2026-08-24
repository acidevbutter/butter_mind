import json
from collections.abc import AsyncIterator
from typing import Any, cast

import openai
from pydantic import BaseModel

from app.core.llm.exceptions import LLMProviderError, LLMRateLimitError
from app.core.llm.schemas import (
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMStructuredResponse,
    LLMUsage,
)


class MaritacaProvider:
    """Wraps the Maritaca AI API (Sabiá models) via its OpenAI-compatible endpoint.

    Only this module talks to the `openai` SDK / Maritaca's base_url — domain
    services depend on the LLMProvider Protocol, never on this class directly.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
    ):
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._model = model

    @staticmethod
    def _input(messages: list[LLMMessage]) -> list[dict[str, str]]:
        """Keep the stable instructions outside the dynamic conversation.

        Maritaca detects identical prompt prefixes automatically. Passing the
        fixed system prompt through ``instructions`` first lets it be reused
        while each visitor message remains the variable tail of the request.
        """
        return [{"role": message.role, "content": message.content} for message in messages]

    @staticmethod
    def _usage(usage: object | None) -> LLMUsage:
        if usage is None:
            return LLMUsage()
        cache_details = getattr(usage, "input_tokens_details", None) or getattr(
            usage, "prompt_tokens_details", None
        )
        return LLMUsage(
            input_tokens=getattr(usage, "input_tokens", None)
            if hasattr(usage, "input_tokens")
            else getattr(usage, "prompt_tokens", None),
            cached_input_tokens=getattr(cache_details, "cached_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None)
            if hasattr(usage, "output_tokens")
            else getattr(usage, "completion_tokens", None),
        )

    @staticmethod
    def _content(response: object) -> str:
        output = getattr(response, "output", [])
        if not output:
            return ""
        content = getattr(output[0], "content", [])
        return getattr(content[0], "text", "") if content else ""

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=cast(Any, self._input(messages)),
                max_output_tokens=max_tokens,
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError(str(exc)) from exc

        return LLMResponse(
            content=self._content(response),
            model=response.model,
            usage=self._usage(response.usage),
        )

    async def complete_stream(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMStreamEvent]:
        try:
            stream = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=cast(Any, self._input(messages)),
                max_output_tokens=max_tokens,
                stream=True,
            )
            async for event_raw in cast(Any, stream):
                event = cast(Any, event_raw)
                if event.type == "response.output_text.delta":
                    delta = event.delta
                    if delta:
                        yield LLMStreamEvent(type="delta", content=delta)
                elif event.type == "response.completed":
                    response = event.response
                    yield LLMStreamEvent(
                        type="completed",
                        response=LLMResponse(
                            content=self._content(response),
                            model=response.model,
                            usage=self._usage(response.usage),
                        ),
                    )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError(str(exc)) from exc

    async def complete_structured(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> LLMStructuredResponse:
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=cast(Any, self._input(messages)),
                max_output_tokens=max_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                        "strict": True,
                    }
                },
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError(str(exc)) from exc

        raw = self._content(response)
        return LLMStructuredResponse(
            data=schema.model_validate(json.loads(raw)),
            response=LLMResponse(
                content=raw, model=response.model, usage=self._usage(getattr(response, "usage", None))
            ),
        )
