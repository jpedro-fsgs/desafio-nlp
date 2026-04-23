import os
import logging
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
import dotenv
from models import RetrievalMode

# Carregar variáveis de ambiente
dotenv.load_dotenv()

# --- SISTEMA DE LOGS ---
logger = logging.getLogger("uvicorn.error")

# Configurações de caminhos
DB_PATH = "data/aneel_legislacao.db"
DOWNLOADS_DIR = "data/downloads"
COLLECTION_NAME = "aneel_metadata"

# Configurações do Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

# Configurações do GCS (GCP Bucket)
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

logger.info("GCP credentials path: " + str(GOOGLE_APPLICATION_CREDENTIALS))

# --- VALIDAÇÃO DE CONFIGURAÇÃO ---

# 1. Validação Qdrant Cloud (Inconsistência de chaves)
if QDRANT_URL or QDRANT_API_KEY:
    if not (QDRANT_URL and QDRANT_API_KEY):
        missing = "QDRANT_API_KEY" if not QDRANT_API_KEY else "QDRANT_URL"
        error_msg = f"Configuração incompleta para Qdrant Cloud: {missing} está faltando no seu arquivo .env"
        logger.error(error_msg)
        raise ValueError(error_msg)

# 2. Validação OpenAI
if not os.getenv("OPENAI_API_KEY"):
    error_msg = "OPENAI_API_KEY não encontrada. O sistema requer esta chave para funcionar."
    logger.error(error_msg)
    raise ValueError(error_msg)

# Modo de recuperação PADRÃO alterado para GCS (Bucket Privado)
RETRIEVAL_MODE = RetrievalMode.GCS 

# 3. Validação GCS se estiver no modo GCS
if RETRIEVAL_MODE == RetrievalMode.GCS:
    if not GCS_BUCKET_NAME or not GOOGLE_APPLICATION_CREDENTIALS:
        error_msg = "Modo GCS ativo, mas GCS_BUCKET_NAME ou GOOGLE_APPLICATION_CREDENTIALS não configurados no .env"
        logger.error(error_msg)
        raise ValueError(error_msg)

# Configurações de Retrieval (Limites Fixos)
SIMILARITY_TOP_K = 2
MAX_RETRIEVAL = 10  # Valor fixo, não alterável via API

# Segurança
API_KEY = os.getenv("API_KEY")

def setup_llama_index():
    """Configura os modelos globais do LlamaIndex."""
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = OpenAI(model="gpt-4o-mini")
    logger.info("Configurações do LlamaIndex inicializadas (Embed: small, LLM: gpt-4o-mini)")
