import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
import qdrant_client
from pypdf import PdfReader
import dotenv

# Carregar variáveis de ambiente
dotenv.load_dotenv()

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileFileHandler("rag_usage.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ANEEL-RAG")

# --- CONFIGURAÇÃO ---
DB_PATH = "data/aneel_legislacao.db"
DOWNLOADS_DIR = "data/downloads"
COLLECTION_NAME = "aneel_metadata"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

# Configuração Global do LlamaIndex
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
Settings.llm = OpenAI(model="gpt-4o-mini")

# Inicializar Cliente Qdrant e Index
client = qdrant_client.QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
index = VectorStoreIndex.from_vector_store(vector_store)
retriever = index.as_retriever(similarity_top_k=2)

# Inicializar FastAPI
app = FastAPI(title="ANEEL RAG API", description="API para consulta de legislação da ANEEL usando RAG.")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[dict]

def get_best_pdf_path(registro_id: int) -> Optional[str]:
    """Busca o melhor arquivo PDF para um registro_id no SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT arquivo FROM pdfs 
        WHERE registro_id = ? 
        ORDER BY CASE 
            WHEN tipo = 'Texto Integral' THEN 1 
            WHEN tipo = 'Voto' THEN 2 
            ELSE 3 
        END 
        LIMIT 1
    """, (registro_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        file_path = os.path.join(DOWNLOADS_DIR, row[0])
        if os.path.exists(file_path):
            return file_path
    return None

def extract_text_from_pdf(pdf_path: str, max_chars: int = 50000) -> str:
    """Extrai texto de um PDF usando pypdf."""
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            if len(text) > max_chars:
                break
    except Exception as e:
        logger.error(f"Erro ao ler PDF {pdf_path}: {e}")
    return text[:max_chars]

@app.post("/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    logger.info(f"Pergunta recebida: '{request.query}'")
    
    # 1. Busca Semântica
    nodes = retriever.retrieve(request.query)
    
    if not nodes:
        logger.warning(f"Nenhum documento encontrado para a query: {request.query}")
        raise HTTPException(status_code=404, detail="Nenhum documento relevante encontrado.")
    
    context_parts = []
    sources = []
    
    for node in nodes:
        reg_id = node.metadata.get("registro_id")
        titulo = node.metadata.get("titulo", "Documento desconhecido")
        
        # 2. Localiza o PDF
        pdf_path = get_best_pdf_path(reg_id)
        
        if pdf_path:
            logger.info(f"Analisando PDF integral: {os.path.basename(pdf_path)} (Registro ID: {reg_id})")
            pdf_text = extract_text_from_pdf(pdf_path)
            context_parts.append(f"--- Documento: {titulo} ---\n{pdf_text}")
            node.metadata["pdf_analisado"] = os.path.basename(pdf_path)
        else:
            logger.info(f"PDF não encontrado. Usando apenas ementa para o registro {reg_id}")
            context_parts.append(f"--- Ementa: {titulo} ---\n{node.text}")
            node.metadata["pdf_analisado"] = "NÃO ENCONTRADO (USOU EMENTA)"

        sources.append(node.metadata)

    full_context = "\n\n".join(context_parts)
    
    # 3. Geração da Resposta
    prompt = f"""
    Você é um assistente jurídico especialista em regulação do setor elétrico brasileiro (ANEEL).
    Use as partes dos documentos fornecidas abaixo para responder à pergunta do usuário de forma clara e profissional.
    Sempre cite o nome da norma em sua resposta.
    
    CONTEXTO:
    {full_context}

    PERGUNTA: {request.query}
    
    RESPOSTA:
    """
    
    response = await Settings.llm.acomplete(prompt)
    logger.info(f"Resposta gerada com sucesso para a query: {request.query[:50]}...")
    
    return QueryResponse(
        query=request.query,
        answer=str(response),
        sources=sources
    )

@app.get("/")
def health_check():
    return {"status": "online", "model": "gpt-4o-mini"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
