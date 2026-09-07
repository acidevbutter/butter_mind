class DisabledEmbeddingsProvider:
    """Stand-in used when RAG_ENABLED is false so torch is never imported.

    Callers must short-circuit before embed_batch; hitting this is a bug.
    """

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("RAG is disabled (RAG_ENABLED=false); embeddings are unavailable")
