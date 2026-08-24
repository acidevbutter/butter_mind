import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import ChatConversation, ChatMessage
from app.chat.schemas import ChatConversationCreate
from app.core.exceptions import NotFoundError


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(self, payload: ChatConversationCreate) -> ChatConversation:
        conversation = ChatConversation(**payload.model_dump())
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation(self, conversation_id: uuid.UUID) -> ChatConversation:
        conversation = await self.session.get(ChatConversation, conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} not found")
        return conversation

    async def list_messages(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        input_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        output_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            model=model,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message
