import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from main import app
import config
import json

# Cliente síncrono para testes básicos
client = TestClient(app)

# Correção de Lint: Garantindo que o token seja string e não None
api_token = str(config.API_KEY) if config.API_KEY else "dummy_token"
AUTH_HEADERS = {"access_token": api_token}

def test_health_check():
    """Valida se a API está online e retorna as configurações corretas."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "retrieval_mode" in data
    assert "similarity_top_k" in data

def test_auth_required():
    """Valida se endpoints protegidos recusam acesso sem token."""
    response = client.post("/ask", json={"query": "teste"})
    assert response.status_code == 403

def test_update_settings_validation():
    """Valida se a API impede configurações inválidas (ex: top_k > 10)."""
    # Caso de erro: top_k muito alto
    response = client.post(
        "/settings/config", 
        headers=AUTH_HEADERS,
        json={"top_k": 20}
    )
    assert response.status_code == 422 

    # Caso de sucesso: alterando para local
    response = client.post(
        "/settings/config",
        headers=AUTH_HEADERS,
        json={"mode": "local", "top_k": 3}
    )
    assert response.status_code == 200
    assert response.json()["retrieval_mode"] == "local"
    assert response.json()["similarity_top_k"] == 3

@pytest.mark.asyncio
async def test_ask_question_real_call():
    """Valida uma consulta RAG real (Small-to-Big) integrada com Qdrant/abstrações."""
    # Resetamos para modo URL para o teste
    client.post("/settings/config", headers=AUTH_HEADERS, json={"mode": "url", "top_k": 1})
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/ask",
            headers=AUTH_HEADERS,
            json={"query": "Quais as regras de tarifas de 2016?"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data

@pytest.mark.asyncio
async def test_chat_stream_real_call():
    """Valida o fluxo de chat streaming (SSE) com o Agente e Workflow v0.14."""
    payload = {
        "session_id": "pytest_session_unique",
        "message": "Resuma a decisão sobre a Light em 2016."
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream("POST", "/chat/stream", headers=AUTH_HEADERS, json=payload) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            events_found = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event_data = json.loads(line.replace("data: ", ""))
                    events_found.append(event_data["type"])
                    if len(events_found) >= 2:
                        break
            
            assert any(e in ["status", "token"] for e in events_found)
