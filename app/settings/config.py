from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://butter_mind:butter_mind@db:5432/butter_mind"

    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    cors_allowed_origin_regex: str | None = None

    maritaca_api_key: str = ""
    maritaca_base_url: str = "https://chat.maritaca.ai/api"
    maritaca_model: str = "sabia-4"

    embeddings_model_name: str = "paraphrase-multilingual-mpnet-base-v2"
    embeddings_dimension: int = 768

    internal_api_key: str = ""


settings = Settings()
