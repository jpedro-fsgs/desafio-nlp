from fastapi import FastAPI, HTTPException
import config
from config import setup_llama_index, logger
from models import QueryRequest, QueryResponse, ConfigSettingsRequest, ConfigResponse
from qdrant_service import get_aneel_query_engine

# 1. Configurar LlamaIndex e Ambiente
setup_llama_index()

# 2. Inicializar FastAPI
app = FastAPI(title="ANEEL RAG API", description="API Modular para consulta de legislação da ANEEL.")

# 3. Inicializar QueryEngine
query_engine = get_aneel_query_engine()

@app.post("/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """Endpoint principal de busca e geração de resposta (RAG)."""
    if not query_engine:
        raise HTTPException(status_code=500, detail="Serviço de consulta indisponível.")
        
    logger.info(f"Pergunta (Modo {config.RETRIEVAL_MODE.value}, Top-K {config.SIMILARITY_TOP_K}): '{request.query[:100]}...'")
    
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

@app.post("/settings/config", response_model=ConfigResponse)
async def update_settings(request: ConfigSettingsRequest):
    """Altera as configurações globais (Modo de Recuperação e Top-K)."""
    if request.mode is not None:
        config.RETRIEVAL_MODE = request.mode
        logger.info(f"Modo de recuperação alterado para: {config.RETRIEVAL_MODE.value}")
    
    if request.top_k is not None:
        config.SIMILARITY_TOP_K = request.top_k
        logger.info(f"Top-K de recuperação alterado para: {config.SIMILARITY_TOP_K}")
    
    return ConfigResponse(
        status="Configurações atualizadas com sucesso",
        retrieval_mode=config.RETRIEVAL_MODE,
        similarity_top_k=config.SIMILARITY_TOP_K,
        max_retrieval=config.MAX_RETRIEVAL
    )

@app.get("/", response_model=ConfigResponse)
def health_check():
    """Retorna o status e as configurações atuais da API."""
    return ConfigResponse(
        status="online",
        retrieval_mode=config.RETRIEVAL_MODE,
        similarity_top_k=config.SIMILARITY_TOP_K,
        max_retrieval=config.MAX_RETRIEVAL
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
