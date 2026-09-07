from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class LocalEmbeddingsProvider:
    """Runs a sentence-transformers model in-process — no external embeddings API.

    SentenceTransformer is imported only on first encode so a process that
    never embeds (RAG_ENABLED=false) never pays the torch import cost.
    """

    def __init__(self, *, model_name: str):
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._get_model().encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
