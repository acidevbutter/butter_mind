import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.chat.repository import ChatRepository
from app.chat.schemas import (
    ChatConversationCreate,
    ChatConversationRead,
    ChatMessageCreate,
    ChatMessageRead,
    GenerateTextRequest,
    GenerateTextResponse,
)
from app.chat.service import ChatService
from app.core.dependencies import DbSession, LLMProviderDep

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service(db: DbSession, llm_provider: LLMProviderDep) -> ChatService:
    return ChatService(ChatRepository(db), llm_provider)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post(
    "/conversations", response_model=ChatConversationRead,
    status_code=status.HTTP_201_CREATED, summary="Start a chat conversation",
)
async def create_conversation(payload: ChatConversationCreate, service: ChatServiceDep) -> ChatConversationRead:
    conversation = await service.create_conversation(payload)
    return ChatConversationRead.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}", response_model=ChatConversationRead,
    summary="Get a chat conversation",
)
async def get_conversation(conversation_id: uuid.UUID, service: ChatServiceDep) -> ChatConversationRead:
    conversation = await service.get_conversation(conversation_id)
    return ChatConversationRead.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[ChatMessageRead],
    summary="List messages in a conversation",
)
async def list_messages(conversation_id: uuid.UUID, service: ChatServiceDep) -> list[ChatMessageRead]:
    await service.get_conversation(conversation_id)
    messages = await service.list_messages(conversation_id)
    return [ChatMessageRead.model_validate(m) for m in messages]


@router.post(
    "/conversations/{conversation_id}/messages", response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED, summary="Send a message and get the assistant's reply",
)
async def send_message(
    conversation_id: uuid.UUID, payload: ChatMessageCreate, service: ChatServiceDep
) -> ChatMessageRead:
    message = await service.send_message(conversation_id=conversation_id, content=payload.content)
    return ChatMessageRead.model_validate(message)


@router.post(
    "/generate", response_model=GenerateTextResponse,
    summary="Generate one-off dynamic text for a site section",
)
async def generate_text(payload: GenerateTextRequest, service: ChatServiceDep) -> GenerateTextResponse:
    text = await service.generate_text(payload)
    return GenerateTextResponse(text=text)
