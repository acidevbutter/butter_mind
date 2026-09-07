from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    debug: bool = False
    log_level: str = "INFO"
    environment: Literal["development", "staging", "preprod", "production"] = "development"

    database_url: str = "postgresql+asyncpg://butter_mind:butter_mind@db:5432/butter_mind"

    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    cors_allowed_origin_regex: str | None = None

    maritaca_api_key: str = ""
    maritaca_base_url: str = "https://chat.maritaca.ai/api"
    maritaca_model: str = "sabia-4"

    embeddings_model_name: str = "paraphrase-multilingual-mpnet-base-v2"
    embeddings_dimension: int = 768
    # Local sentence-transformers embeddings stay off until a GPU host is
    # available. Chat/diagnosis still run via the Maritaca API.
    rag_enabled: bool = False

    internal_api_key: str = ""

    # Shared key required on the public diagnosis/chat endpoints (proves the
    # caller is devbutter_backend, not a browser hitting the API directly).
    # Distinct from internal_api_key, which gates the small internal/admin
    # audience (dashboard, CRM sync), not the public-facing flows.
    service_api_key: str = ""

    # Fixed token/cost governance for the diagnosis chat flow (see
    # docs/mapa-chat-widget-metricas-tokens.md §2.3) — replaces the previous
    # unbounded "send the whole history every turn" behavior with three caps
    # that make the max cost per session a known, computable number.
    diagnosis_max_output_tokens: int = 1024
    diagnosis_max_history_messages: int = 12
    diagnosis_max_turns: int = 30
    diagnosis_grounding_top_k: int = 3
    diagnosis_grounding_min_score: float = 0.35


settings = Settings()
