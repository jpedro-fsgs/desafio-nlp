import qdrant_client
from qdrant_client import AsyncQdrantClient
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer, ResponseMode

import config
from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_URL, QDRANT_API_KEY, 
    COLLECTION_REGISTROS, COLLECTION_PDFS, logger
)
# Importa o retriever e o fetcher do módulo correto
from services.gcs import GCSFullDocumentRetriever

def get_qdrant_client():
    """Retorna um cliente Qdrant baseado nas configurações de ambiente."""
    if QDRANT_URL and QDRANT_API_KEY:
        logger.info(f"Conectando ao Qdrant Cloud em {QDRANT_URL}")
        return qdrant_client.QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        )
    else:
        logger.info(f"Conectando ao Qdrant Local em {QDRANT_HOST}:{QDRANT_PORT}")
        return qdrant_client.QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
        )

def get_async_qdrant_client():
    """Retorna um cliente Qdrant ASSÍNCRONO baseado nas configurações de ambiente."""
    if QDRANT_URL and QDRANT_API_KEY:
        return AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    else:
        return AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def get_registros_query_engine():
    """Retorna um QueryEngine para a coleção de registros (Macro)."""
    try:
        client = get_qdrant_client()
        aclient = get_async_qdrant_client()
        # Define text_key="ementa" pois é onde o conteúdo textual está nesta coleção
        vector_store = QdrantVectorStore(
            client=client, 
            aclient=aclient, 
            collection_name=COLLECTION_REGISTROS,
            text_key="ementa"
        )
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        return index.as_query_engine(
            similarity_top_k=config.SIMILARITY_TOP_K,
            response_mode=ResponseMode.COMPACT
        )
    except Exception as e:
        logger.error(f"Falha ao inicializar Registros QueryEngine: {e}")
        raise RuntimeError(f"Base de registros indisponível: {e}")

def get_pdfs_query_engine():
    """Retorna um QueryEngine para a coleção de PDFs com Parent Retrieval via GCS."""
    try:
        client = get_qdrant_client()
        aclient = get_async_qdrant_client()
        # Define text_key="texto" pois é o nome usado no payload dos chunks
        vector_store = QdrantVectorStore(
            client=client, 
            aclient=aclient, 
            collection_name=COLLECTION_PDFS,
            text_key="texto"
        )
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        # Retriever base (vetorial)
        base_retriever = index.as_retriever(similarity_top_k=config.SIMILARITY_TOP_K)
        
        # Retriever customizado (GCS Parent) - Agora importado de services.gcs
        custom_retriever = GCSFullDocumentRetriever(base_retriever)
        
        return RetrieverQueryEngine(
            retriever=custom_retriever,
            response_synthesizer=get_response_synthesizer(response_mode=ResponseMode.COMPACT)
        )
    except Exception as e:
        logger.error(f"Falha ao inicializar PDFs QueryEngine: {e}")
        raise RuntimeError(f"Base de documentos técnicos indisponível: {e}")
