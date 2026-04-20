import os
import logging
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
import dotenv
from models import RetrievalMode

# Carregar variáveis de ambiente
dotenv.load_dotenv()

# Configurações de caminhos e serviços
DB_PATH = "data/aneel_legislacao.db"
DOWNLOADS_DIR = "data/downloads"
COLLECTION_NAME = "aneel_metadata"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

# Modo de recuperação: 'local' ou 'url' (Usando Enum)
RETRIEVAL_MODE = RetrievalMode.URL 


# --- SISTEMA DE LOGS ---
# Recupera o logger do uvicorn para integração perfeita com o console
logger = logging.getLogger("uvicorn.error")

def setup_llama_index():
    """Configura os modelos globais do LlamaIndex."""
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = OpenAI(model="gpt-4o-mini")
    logger.info("Configurações do LlamaIndex inicializadas (Embed: small, LLM: gpt-4o-mini)")
