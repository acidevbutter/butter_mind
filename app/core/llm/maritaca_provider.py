import json

import openai
from pydantic import BaseModel

from app.core.llm.exceptions import LLMProviderError, LLMRateLimitError
from app.core.llm.schemas import LLMMessage, LLMResponse, LLMUsage


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
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._model, messages=payload, max_tokens=max_tokens,
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError(str(exc)) from exc

        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
            ),
        )

    async def complete_structured(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel:
        conversation = "\n".join(f"{m.role}: {m.content}" for m in messages)
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=conversation,
                max_output_tokens=max_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    }
                },
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError(str(exc)) from exc

        raw = response.output[0].content[0].text
        return schema.model_validate(json.loads(raw))
