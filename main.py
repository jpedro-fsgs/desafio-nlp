from fastapi import FastAPI, HTTPException
import config
from config import setup_llama_index, logger
from models import QueryRequest, QueryResponse, RetrievalModeRequest
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
        
    logger.info(f"Pergunta (Modo {config.RETRIEVAL_MODE.value}): '{request.query[:100]}...'")
    
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

@app.post("/settings/retrieval-mode")
async def set_retrieval_mode(request: RetrievalModeRequest):
    """Altera o modo de recuperação entre 'local' e 'url' usando Enums."""
    config.RETRIEVAL_MODE = request.mode
    logger.info(f"Modo de recuperação alterado para: {config.RETRIEVAL_MODE.value}")
    return {"message": f"Modo de recuperação alterado para {config.RETRIEVAL_MODE.value}"}

@app.get("/")
def health_check():
    return {
        "status": "online", 
        "current_retrieval_mode": config.RETRIEVAL_MODE.value
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
