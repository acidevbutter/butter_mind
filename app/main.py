from fastapi import FastAPI

from app.chat.router import router as chat_router
from app.core.exceptions import register_exception_handlers
from app.diagnosis.router import router as diagnosis_router
from app.knowledge.router import router as knowledge_router
from app.llm_usage.router import router as llm_usage_router
from app.settings.config import settings
from app.settings.logging_config import setup_logging
from app.settings.middleware import register_middleware

setup_logging(settings.log_level)

app = FastAPI(title="DevButter Backend API")
register_middleware(app)
register_exception_handlers(app)
app.include_router(chat_router)
app.include_router(diagnosis_router)
app.include_router(knowledge_router)
app.include_router(llm_usage_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
