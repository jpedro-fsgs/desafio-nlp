from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
import config
from config import setup_llama_index, logger
from models import QueryRequest, QueryResponse, ConfigSettingsRequest, ConfigResponse
from qdrant_service import get_aneel_query_engine
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

# 3. Inicializar QueryEngine
query_engine = get_aneel_query_engine()

@app.post("/ask", response_model=QueryResponse, dependencies=[Depends(get_api_key)])
async def ask_question(request: QueryRequest):
    """Endpoint principal de busca e geração de resposta (Protegido)."""
    if not query_engine:
        raise HTTPException(status_code=500, detail="Serviço de consulta indisponível.")
        
    logger.info(f"Pergunta (Modo {config.RETRIEVAL_MODE.value}): '{request.query[:50]}...'")
    
    try:
        response = await query_engine.aquery(request.query)
        sources = [node.metadata for node in response.source_nodes]
        return QueryResponse(
            query=request.query,
            answer=str(response),
            sources=sources
        )
    except Exception as e:
        logger.error(f"Erro no RAG: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar a pergunta.")

@app.post("/settings/config", response_model=ConfigResponse, dependencies=[Depends(get_api_key)])
async def update_settings(request: ConfigSettingsRequest):
    """Altera as configurações globais (Protegido)."""
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
    """Health check público para monitoramento básico."""
    return ConfigResponse(
        status="online",
        retrieval_mode=config.RETRIEVAL_MODE,
        similarity_top_k=config.SIMILARITY_TOP_K,
        max_retrieval=config.MAX_RETRIEVAL
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
