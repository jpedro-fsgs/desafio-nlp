import qdrant_client
from typing import List
from llama_index.core import VectorStoreIndex, QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer, ResponseMode

import config
from config import QDRANT_HOST, QDRANT_PORT, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME, logger
from pipeline.orchestrator import DocumentPipeline

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

class AneelRetriever(BaseRetriever):
    """Retriever customizado que implementa a estratégia Small-to-Big.
    Busca a ementa no Qdrant e usa o DocumentPipeline para recuperar o texto integral.
    """
    def __init__(self, vector_retriever: BaseRetriever):
        self._vector_retriever = vector_retriever
        self._pipeline = DocumentPipeline()
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # Atualiza dinamicamente o Top-K do retriever base usando setattr
        if hasattr(self._vector_retriever, "similarity_top_k"):
            setattr(self._vector_retriever, "similarity_top_k", config.SIMILARITY_TOP_K)
        elif hasattr(self._vector_retriever, "_similarity_top_k"):
            setattr(self._vector_retriever, "_similarity_top_k", config.SIMILARITY_TOP_K)

        # 1. Busca as ementas no Qdrant
        nodes_with_score = self._vector_retriever.retrieve(query_bundle)
        
        final_nodes: List[NodeWithScore] = []
        for node_with_score in nodes_with_score:
            reg_id = node_with_score.node.metadata.get("registro_id")
            
            if reg_id is None or not isinstance(reg_id, int):
                final_nodes.append(node_with_score)
                continue
            
            # 2. Orquestração Modular: Metadados -> Fetch -> Parse
            full_text, origem = self._pipeline.process_document(reg_id, config.RETRIEVAL_MODE)

            if full_text:
                new_node = TextNode(
                    text=full_text,
                    metadata=node_with_score.node.metadata
                )
                new_node.metadata["fonte_tipo"] = origem
                final_nodes.append(NodeWithScore(node=new_node, score=node_with_score.score))
            else:
                node_with_score.node.metadata["fonte_tipo"] = f"{origem} (Fallback Ementa)"
                final_nodes.append(node_with_score)
                
        return final_nodes

def get_aneel_query_engine():
    """Inicializa e retorna um QueryEngine completo."""
    try:
        client = get_qdrant_client()
        vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        base_retriever = index.as_retriever(similarity_top_k=config.SIMILARITY_TOP_K)
        custom_retriever = AneelRetriever(base_retriever)
        
        response_synthesizer = get_response_synthesizer(response_mode=ResponseMode.COMPACT)
        
        query_engine = RetrieverQueryEngine(
            retriever=custom_retriever,
            response_synthesizer=response_synthesizer
        )
        
        return query_engine
    except Exception as e:
        logger.error(f"Falha ao inicializar QueryEngine: {e}")
        return None
