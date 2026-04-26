from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import StreamingResponse
import config
from config import setup_llama_index, logger
from models import (
    QueryRequest, QueryResponse, ConfigSettingsRequest, ConfigResponse, 
    ChatRequest, TitleRequest, TitleResponse, SourceModel
)
from services.qdrant import get_registros_query_engine
from agent.service import astream_agent_chat, generate_chat_title_service, get_user_chats_service, delete_chat_service
from starlette.status import HTTP_403_FORBIDDEN

# 1. Configurar LlamaIndex e Ambiente
setup_llama_index()

# 2. Inicializar FastAPI
app = FastAPI(title="ANEEL RAG API", description="API Modular e Segura para consulta de legislação da ANEEL.")

# Segurança: API Key
API_KEY_NAME = "access_token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Depends(api_key_header)):
    if api_key_header == config.API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN, detail="Acesso negado: API Key inválida ou ausente."
    )

# 3. Inicializar QueryEngine (Modo Legado/Direto - Usando Registros como default)
query_engine = get_registros_query_engine()

@app.post("/ask", response_model=QueryResponse, dependencies=[Depends(get_api_key)])
async def ask_question(request: QueryRequest):
    """Endpoint direto de busca e geração de resposta (Sem memória)."""
    if not query_engine:
        raise HTTPException(status_code=500, detail="Serviço de consulta indisponível.")
        
    logger.info(f"Pergunta Direta (Modo {config.RETRIEVAL_MODE.value}): '{request.query[:50]}...'")
    
    try:
        response = await query_engine.aquery(request.query)
        sources = []
        for node_with_score in response.source_nodes:
            m = node_with_score.node.metadata
            link = m.get('pdf_url_acesso') 

            sources.append(SourceModel(
                id=str(m.get('registro_id') or m.get('pdf_nome') or "src"),
                title=m.get('pdf_nome') or m.get('titulo') or "Documento",
                link=link,
                # Se houver link, é um PDF: mantemos apenas o link (text=None)
                # Se não houver link, é um registro: mostramos a ementa (collapsible)
                text=node_with_score.node.get_content() if not link else None,
                tool_name="retrieval_direto"
            ))
            
        return QueryResponse(
            query=request.query,
            answer=str(response),
            sources=sources
        )
    except Exception as e:
        logger.error(f"Erro no RAG: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar a pergunta.")

@app.post("/chat/stream", dependencies=[Depends(get_api_key)])
async def chat_streaming(request: ChatRequest):
    """Endpoint de chat interativo com Agente, Memória e Streaming de estados."""
    logger.info(f"Nova mensagem no chat (User: {request.user_id}, Session: {request.session_id})")
    return StreamingResponse(
        astream_agent_chat(request.session_id, request.message, request.user_id),
        media_type="text/event-stream"
    )

@app.post("/chat/title", response_model=TitleResponse, dependencies=[Depends(get_api_key)])
async def generate_chat_title(request: TitleRequest):
    """Gera um título curto para a sessão de chat baseado na primeira mensagem."""
    title = await generate_chat_title_service(request.message, request.session_id, request.user_id)
    return TitleResponse(title=title)

@app.get("/users/{user_id}/chats", dependencies=[Depends(get_api_key)])
async def get_user_chats(user_id: str):
    """Recupera todas as sessões e históricos associados a um usuário (em memória)."""
    return get_user_chats_service(user_id)

@app.delete("/chats/{session_id}", dependencies=[Depends(get_api_key)])
async def delete_chat(session_id: str):
    """Deleta uma sessão específica da memória."""
    delete_chat_service(session_id)
    return {"status": "deleted"}

@app.post("/settings/config", response_model=ConfigResponse, dependencies=[Depends(get_api_key)])
async def update_settings(request: ConfigSettingsRequest):
    """Altera as configurações globais."""
    if request.mode is not None:
        config.RETRIEVAL_MODE = request.mode
    
    if request.top_k is not None:
        config.SIMILARITY_TOP_K = request.top_k
    
    return ConfigResponse(
        status="Configurações atualizadas com sucesso",
        retrieval_mode=config.RETRIEVAL_MODE,
        similarity_top_k=config.SIMILARITY_TOP_K,
        max_retrieval=config.MAX_RETRIEVAL
    )

@app.get("/", response_model=ConfigResponse)
def health_check():
    """Health check público."""
    return ConfigResponse(
        status="online",
        retrieval_mode=config.RETRIEVAL_MODE,
        similarity_top_k=config.SIMILARITY_TOP_K,
        max_retrieval=config.MAX_RETRIEVAL
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
