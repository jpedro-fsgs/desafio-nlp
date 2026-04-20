import qdrant_client
from typing import List
from llama_index.core import VectorStoreIndex, QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, logger
from utils import get_best_pdf_path, extract_text_from_pdf

class AneelRetriever(BaseRetriever):
    """Retriever customizado que implementa a estratégia Small-to-Big.
    Busca a ementa no Qdrant e retorna o texto integral do PDF como contexto.
    """
    def __init__(self, vector_retriever: BaseRetriever):
        self._vector_retriever = vector_retriever
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # 1. Busca as ementas no Qdrant
        nodes_with_score = self._vector_retriever.retrieve(query_bundle)
        
        final_nodes = []
        for node_with_score in nodes_with_score:
            reg_id = node_with_score.node.metadata.get("registro_id")
            titulo = node_with_score.node.metadata.get("titulo")
            
            # 2. Busca o PDF correspondente
            pdf_path = get_best_pdf_path(reg_id)
            
            if pdf_path:
                # 3. Extrai o texto integral
                full_text = extract_text_from_pdf(pdf_path)
                # Cria um novo nó com o texto completo para o sintetizador
                new_node = TextNode(
                    text=full_text,
                    metadata=node_with_score.node.metadata
                )
                new_node.metadata["fonte_tipo"] = "PDF Integral"
                
                final_nodes.append(NodeWithScore(node=new_node, score=node_with_score.score))
            else:
                # Fallback para a própria ementa se o PDF falhar
                node_with_score.node.metadata["fonte_tipo"] = "Ementa (Fallback)"
                final_nodes.append(node_with_score)
                
        return final_nodes

def get_aneel_query_engine():
    """Inicializa e retorna um QueryEngine completo que retorna objetos Response."""
    try:
        client = qdrant_client.QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        # Cria o retriever base do Qdrant
        base_retriever = index.as_retriever(similarity_top_k=2)
        
        # Envolve no nosso retriever customizado (Small-to-Big)
        custom_retriever = AneelRetriever(base_retriever)
        
        # Cria o Query Engine a partir do retriever customizado
        from llama_index.core.query_engine import RetrieverQueryEngine
        from llama_index.core.response_synthesizers import get_response_synthesizer
        
        response_synthesizer = get_response_synthesizer(response_mode="compact")
        
        query_engine = RetrieverQueryEngine(
            retriever=custom_retriever,
            response_synthesizer=response_synthesizer
        )
        
        logger.info(f"QueryEngine da ANEEL inicializado com sucesso.")
        return query_engine
    except Exception as e:
        logger.error(f"Falha ao inicializar QueryEngine: {e}")
        return None
