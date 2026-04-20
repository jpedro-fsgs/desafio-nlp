from fastapi import FastAPI, HTTPException
from config import setup_llama_index, logger
from models import QueryRequest, QueryResponse
from qdrant_service import get_aneel_query_engine

# 1. Configurar LlamaIndex e Ambiente
setup_llama_index()

# 2. Inicializar FastAPI
app = FastAPI(title="ANEEL RAG API", description="API Modular e Idiomática para consulta de legislação da ANEEL.")

# 3. Inicializar QueryEngine (Orquestra Retriever Customizado + Sintetizador)
query_engine = get_aneel_query_engine()

@app.post("/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """Endpoint principal que utiliza um QueryEngine para retornar um objeto Response."""
    if not query_engine:
        logger.error("QueryEngine não inicializado corretamente.")
        raise HTTPException(status_code=500, detail="Serviço de consulta indisponível.")
        
    logger.info(f"Pergunta (Idiomática): '{request.query[:100]}...'")
    
    try:
        # A chamada aquery agora faz TUDO: busca ementa, lê PDF e sintetiza resposta
        response = await query_engine.aquery(request.query)
        
        # Extrai metadados das fontes do objeto Response
        sources = [node.metadata for node in response.source_nodes]
        
        logger.info(f"Resposta gerada com sucesso. Fontes utilizadas: {len(sources)}")
        
        return QueryResponse(
            query=request.query,
            answer=str(response),
            sources=sources
        )
        
    except Exception as e:
        logger.error(f"Erro durante a execução do QueryEngine: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar a pergunta.")

@app.get("/")
def health_check():
    return {"status": "online", "mode": "idiomatic-response"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
