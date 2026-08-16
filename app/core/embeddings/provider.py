from typing import Protocol


class EmbeddingsProvider(Protocol):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...
