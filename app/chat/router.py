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
from app.core.dependencies import DbSession, LLMProviderDep, RequireServiceApiKey
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service(db: DbSession, llm_provider: LLMProviderDep) -> ChatService:
    return ChatService(ChatRepository(db), llm_provider, LLMUsageService(LLMUsageRepository(db)))


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post(
    "/conversations", response_model=ChatConversationRead,
    status_code=status.HTTP_201_CREATED, summary="Start a chat conversation",
    dependencies=[RequireServiceApiKey],
    description=(
        "Creates a new chat conversation and returns its identifier. "
        "Use this to open a fresh thread before sending any messages, e.g. when a visitor "
        "opens the chat widget on the site for the first time or starts a new topic."
    ),
)
async def create_conversation(payload: ChatConversationCreate, service: ChatServiceDep) -> ChatConversationRead:
    conversation = await service.create_conversation(payload)
    return ChatConversationRead.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}", response_model=ChatConversationRead,
    summary="Get a chat conversation",
    dependencies=[RequireServiceApiKey],
    description=(
        "Fetches metadata for a single conversation by id. "
        "Use this to restore a chat session on page reload or to confirm a conversation "
        "still exists before posting messages to it."
    ),
)
async def get_conversation(conversation_id: uuid.UUID, service: ChatServiceDep) -> ChatConversationRead:
    conversation = await service.get_conversation(conversation_id)
    return ChatConversationRead.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[ChatMessageRead],
    summary="List messages in a conversation",
    dependencies=[RequireServiceApiKey],
    description=(
        "Returns the full message history for a conversation, in order. "
        "Use this to render the chat transcript when a user reopens a previous conversation "
        "or to build context for analytics/moderation."
    ),
)
async def list_messages(conversation_id: uuid.UUID, service: ChatServiceDep) -> list[ChatMessageRead]:
    await service.get_conversation(conversation_id)
    messages = await service.list_messages(conversation_id)
    return [ChatMessageRead.model_validate(m) for m in messages]


@router.post(
    "/conversations/{conversation_id}/messages", response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED, summary="Send a message and get the assistant's reply",
    dependencies=[RequireServiceApiKey],
    description=(
        "Appends a user message to the conversation, runs it through the LLM provider, "
        "and returns the assistant's reply. Use this for the core turn-by-turn chat "
        "interaction, e.g. a visitor asking a question in a support widget."
    ),
)
async def send_message(
    conversation_id: uuid.UUID, payload: ChatMessageCreate, service: ChatServiceDep
) -> ChatMessageRead:
    message = await service.send_message(conversation_id=conversation_id, content=payload.content)
    return ChatMessageRead.model_validate(message)


@router.post(
    "/generate", response_model=GenerateTextResponse,
    summary="Generate one-off dynamic text for a site section",
    dependencies=[RequireServiceApiKey],
    description=(
        "Generates a single piece of text with no persisted conversation state. "
        "Use this for stateless content generation such as a dynamic hero headline, "
        "product blurb, or personalized snippet embedded in a page section."
    ),
)
async def generate_text(payload: GenerateTextRequest, service: ChatServiceDep) -> GenerateTextResponse:
    text = await service.generate_text(payload)
    return GenerateTextResponse(text=text)
