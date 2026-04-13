import os
import sqlite3
import asyncio
from llama_index.core import Document, StorageContext, VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import QdrantClient
import dotenv

# Carregar variáveis de ambiente (necessário para OPENAI_API_KEY)
dotenv.load_dotenv()

# --- CONFIGURAÇÃO ---
DB_PATH = "data/aneel_legislacao.db"
QDRANT_HOST = "localhost" # Altere para o host do container se necessário
QDRANT_PORT = 6333
COLLECTION_NAME = "aneel_metadata"

# Configurar Embeddings (IMPORTANTE: não mude o modelo após indexar!)
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

def load_metadata_from_sqlite():
    """Lê os metadados do SQLite e os transforma em objetos Document."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Banco de dados {DB_PATH} não encontrado.")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Busca os registros normalizados
    cursor.execute("""
        SELECT id, titulo, autor, material, esfera, situacao, assinatura, publicacao, assunto, ementa 
        FROM registros
    """)
    rows = cursor.fetchall()
    conn.close()

    documents = []
    print(f"Preparando {len(rows)} documentos para indexação...")

    for row in rows:
        reg_id, titulo, autor, material, esfera, situacao, assinatura, publicacao, assunto, ementa = row
        
        # Lógica de Fallback: Se não houver ementa, usa Título + Assunto
        text_to_embed = ementa if (ementa and len(ementa.strip()) > 5) else f"{titulo}. Assunto: {assunto}"
        
        # Criar o documento
        doc = Document(
            text=text_to_embed,
            id_=str(reg_id), # ID original do banco para facilitar o cruzamento
            metadata={
                "registro_id": reg_id,
                "titulo": titulo or "",
                "autor": autor or "",
                "situacao": situacao or "",
                "assunto": assunto or "",
                "data_publicacao": publicacao or "",
                "tipo_ato": titulo.split(" - ")[0] if " - " in (titulo or "") else "OUTRO"
            }
        )
        # Excluir metadados técnicos do prompt do LLM se necessário, 
        # mas mantê-los para filtragem no Qdrant.
        doc.excluded_embed_metadata_keys = ["registro_id"]
        
        documents.append(doc)
    
    return documents

async def run_indexing():
    # 1. Carregar documentos
    documents = load_metadata_from_sqlite()

    # 2. Inicializar cliente Qdrant
    print(f"Conectando ao Qdrant em {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # 3. Configurar Vector Store e Storage Context
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 4. Criar o Índice (Isso gera os embeddings via OpenAI)
    print("Iniciando geração de embeddings e indexação (isso pode levar alguns minutos)...")
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True
    )

    print(f"\n[OK] Indexação concluída! Coleção '{COLLECTION_NAME}' criada no Qdrant.")

if __name__ == "__main__":
    asyncio.run(run_indexing())
