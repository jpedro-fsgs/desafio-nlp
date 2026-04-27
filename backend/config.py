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
DOWNLOADS_DIR = "data/downloads"
COLLECTION_REGISTROS = "aneel_registros"
COLLECTION_PDFS = "aneel_pdfs"

# Configurações do Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

# Configurações de Cloud e LLM
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

# OpenAI Model Config
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Segurança da API Interna
API_KEY = os.getenv("API_KEY")

# --- VALIDAÇÃO DE CONFIGURAÇÃO ---


def validate_config():
    """Valida as configurações críticas e loga erros detalhados."""
    errors = []

    # 1. Validação Qdrant
    if QDRANT_URL or QDRANT_API_KEY:
        if not QDRANT_URL:
            errors.append("QDRANT_URL ausente mesmo com QDRANT_API_KEY definida.")
        if not QDRANT_API_KEY:
            errors.append("QDRANT_API_KEY ausente mesmo com QDRANT_URL definida.")

    # 2. Validação OpenAI (LLM e Embeddings)
    if not os.getenv("OPENAI_API_KEY"):
        errors.append(
            "OPENAI_API_KEY não encontrada. Necessária para o LLM e busca vetorial (embeddings)."
        )

    # 3. Validação Google Credentials (GCS)
    if not GOOGLE_APPLICATION_CREDENTIALS:
        logger.warning(
            "GOOGLE_APPLICATION_CREDENTIALS não definido. Acesso ao GCS falhará se necessário."
        )

    if not GCS_BUCKET_NAME:
        logger.warning(
            "GCS_BUCKET_NAME não definido. Operações de armazenamento e recuperação de documentos falharão."
        )

    # 4. Validação do Modelo OpenAI
    if not OPENAI_MODEL:
        errors.append("OPENAI_MODEL não definido. Especifique o modelo a ser usado para o LLM.")

    # 5. Validação da Chave da API
    if not API_KEY:
        logger.warning(
            "API_KEY não definida."
        )


    if errors:
        for err in errors:
            logger.error(f"[CONFIG ERROR] {err}")


validate_config()

# Modo de recuperação PADRÃO
RETRIEVAL_MODE = RetrievalMode.GCS

# Configurações de Retrieval
SIMILARITY_TOP_K = 3
MAX_RETRIEVAL = 10


def setup_llama_index():
    """Configura os modelos globais utilizando OpenAI para LLM e Embeddings."""
    try:
        # OpenAI para Embeddings (Consistência com a base indexada no Qdrant)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

        Settings.llm = OpenAI(model=OPENAI_MODEL)

        logger.info(
            f"LlamaIndex inicializado: LLM={OPENAI_MODEL}, Embed=OpenAI-small"
        )
    except Exception as e:
        logger.error(f"[FATAL] Falha ao configurar LlamaIndex: {str(e)}")
        raise
