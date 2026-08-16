from sentence_transformers import SentenceTransformer


class LocalEmbeddingsProvider:
    """Runs a sentence-transformers model in-process — no external embeddings API.

    The model is loaded lazily on first use (not at construction time) so
    importing this module — e.g. for the DI wiring in core/dependencies.py —
    doesn't pay the model-load cost until an embedding is actually requested.
    """

    def __init__(self, *, model_name: str):
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._get_model().encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
