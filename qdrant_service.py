import qdrant_client
import time
import random
from typing import List
from llama_index.core import VectorStoreIndex, QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer, ResponseMode

import config
from models import RetrievalMode
from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, logger
from utils import get_best_pdf_info, extract_text_from_pdf, extract_text_from_url

class AneelRetriever(BaseRetriever):
    """Retriever customizado que implementa a estratégia Small-to-Big.
    Busca a ementa no Qdrant e retorna o texto integral do PDF como contexto.
    Respeita o modo de recuperação (local ou url) definido em config.
    """
    def __init__(self, vector_retriever: BaseRetriever):
        self._vector_retriever = vector_retriever
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # 1. Busca as ementas no Qdrant
        nodes_with_score = self._vector_retriever.retrieve(query_bundle)
        
        final_nodes: List[NodeWithScore] = []
        for i, node_with_score in enumerate(nodes_with_score):
            reg_id_raw = node_with_score.node.metadata.get("registro_id")
            
            if reg_id_raw is None or not isinstance(reg_id_raw, int):
                final_nodes.append(node_with_score)
                continue
                
            reg_id: int = reg_id_raw
            pdf_path, pdf_url = get_best_pdf_info(reg_id)
            
            full_text = ""
            origem = "Fallback (Ementa)"

            # 3. Recuperação baseada no Modo Ativo
            if config.RETRIEVAL_MODE == RetrievalMode.URL and pdf_url:
                # Intervalo ALEATÓRIO entre 2 e 5 segundos para quebrar o padrão rítmico
                if i > 0:
                    delay = random.uniform(2.0, 5.0)
                    time.sleep(delay)
                    
                full_text = extract_text_from_url(pdf_url)
                origem = "URL Direta"
            
            elif config.RETRIEVAL_MODE == RetrievalMode.LOCAL and pdf_path:
                full_text = extract_text_from_pdf(pdf_path)
                origem = "PDF Local"

            if full_text:
                new_node = TextNode(
                    text=full_text,
                    metadata=node_with_score.node.metadata
                )
                new_node.metadata["fonte_tipo"] = origem
                final_nodes.append(NodeWithScore(node=new_node, score=node_with_score.score))
            else:
                node_with_score.node.metadata["fonte_tipo"] = "Ementa (Fallback)"
                final_nodes.append(node_with_score)
                
        return final_nodes

def get_aneel_query_engine():
    """Inicializa e retorna um QueryEngine completo."""
    try:
        client = qdrant_client.QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        base_retriever = index.as_retriever(similarity_top_k=2)
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
