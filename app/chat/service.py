import uuid

from app.chat.models import ChatConversation, ChatMessage
from app.chat.repository import ChatRepository
from app.chat.schemas import ChatConversationCreate, GenerateTextRequest
from app.core.decorators import log_errors
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage
from app.llm_usage.service import LLMUsageService
from app.settings.config import settings

CHAT_SYSTEM_PROMPT = (
    "Você é o assistente virtual da DevButter, um estúdio de tecnologia que combina "
    "engenharia, ciência e criatividade para construir produtos de software e IA sob medida. "
    "Responda em português do Brasil, de forma clara, cordial e objetiva."
)

GENERATE_SYSTEM_PROMPT = (
    "Você gera pequenos textos para o site da DevButter, um estúdio de tecnologia. "
    "Escreva em português do Brasil, no tom da marca: direto, confiante e sem jargão vazio."
)


@log_errors
class ChatService:
    def __init__(
        self, repository: ChatRepository, llm_provider: LLMProvider, llm_usage_service: LLMUsageService
    ):
        self.repository = repository
        self.llm_provider = llm_provider
        self.llm_usage_service = llm_usage_service

    async def create_conversation(self, payload: ChatConversationCreate) -> ChatConversation:
        return await self.repository.create_conversation(payload)

    async def get_conversation(self, conversation_id: uuid.UUID) -> ChatConversation:
        return await self.repository.get_conversation(conversation_id)

    async def list_messages(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        return await self.repository.list_messages(conversation_id)

    async def send_message(self, *, conversation_id: uuid.UUID, content: str) -> ChatMessage:
        await self.repository.get_conversation(conversation_id)
        await self.repository.add_message(conversation_id=conversation_id, role="user", content=content)

        history = await self.repository.list_messages(conversation_id)
        llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]

        await self.llm_usage_service.ensure_budget(
            flow="general_chat",
            model=settings.maritaca_model,
            system=CHAT_SYSTEM_PROMPT,
            messages=llm_messages,
            max_tokens=4096,
        )
        response = await self.llm_provider.complete(
            system=CHAT_SYSTEM_PROMPT,
            messages=llm_messages,
        )
        await self.llm_usage_service.record(
            flow="general_chat", operation="reply", response=response
        )

        return await self.repository.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.content,
            input_tokens=response.usage.input_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    async def generate_text(self, payload: GenerateTextRequest) -> str:
        context_str = "\n".join(f"{k}: {v}" for k, v in payload.context.items())
        prompt = f"{payload.prompt}\n\nContexto:\n{context_str}" if context_str else payload.prompt
        messages = [LLMMessage(role="user", content=prompt)]
        await self.llm_usage_service.ensure_budget(
            flow="site_text_generation",
            model=settings.maritaca_model,
            system=GENERATE_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=payload.max_tokens,
        )
        response = await self.llm_provider.complete(
            system=GENERATE_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=payload.max_tokens,
        )
        await self.llm_usage_service.record(
            flow="site_text_generation", operation="generate", response=response
        )
        return response.content
