from app.core.dependencies import get_llm_provider
from app.main import app
from tests.factories import FakeLLMProvider


async def test_create_conversation_and_send_message(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Olá! Como posso ajudar?")

    created = await client.post("/chat/conversations", json={"session_id": "abc123"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    response = await client.post(
        f"/chat/conversations/{conversation_id}/messages", json={"content": "Oi"}
    )
    assert response.status_code == 201
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "Olá! Como posso ajudar?"

    history = await client.get(f"/chat/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2


async def test_generate_text(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Texto gerado.")

    response = await client.post("/chat/generate", json={"prompt": "Escreva uma frase curta."})
    assert response.status_code == 200
    assert response.json()["text"] == "Texto gerado."


async def test_get_missing_conversation_returns_404(client):
    response = await client.get("/chat/conversations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
