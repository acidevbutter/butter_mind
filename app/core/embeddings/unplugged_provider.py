from typing import Literal


class UnpluggedEmbeddingsProvider:
    """Placeholder for a remote embeddings API (OpenAI or Anthropic) that is
    not wired up yet -- embed_batch always raises. No SDK/model dependency is
    needed just to describe which API a future implementation should call.
    """

    def __init__(
        self,
        *,
        provider: Literal["openai", "anthropic"],
        model_name: str,
    ):
        self._provider = provider
        self._model_name = model_name

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # TODO: call the OpenAI or Anthropic embeddings API using
        # self._provider / self._model_name / settings.embeddings_api_key.
        raise NotImplementedError(
            f"Embeddings are unplugged: no {self._provider} client is wired up yet "
            f"(model={self._model_name!r})"
        )
