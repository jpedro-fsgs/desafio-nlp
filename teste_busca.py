import os
import qdrant_client
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
import dotenv

dotenv.load_dotenv()

# Configuração igual à da indexação
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
client = qdrant_client.QdrantClient(host="localhost", port=6333)
vector_store = QdrantVectorStore(client=client, collection_name="aneel_metadata")

# Carregar o índice (sem precisar re-indexar nada)
index = VectorStoreIndex.from_vector_store(vector_store)

def testar_busca(query):
    print(f"\n--- Pergunta: {query} ---")
    retriever = index.as_retriever(similarity_top_k=3)
    nodes = retriever.retrieve(query)
    
    for i, node in enumerate(nodes):
        print(f"\nResultado {i+1} (Score: {node.score:.4f}):")
        print(f"Título: {node.metadata.get('titulo')}")
        print(f"Ementa/Texto: {node.text[:200]}...")
        print(f"Data: {node.metadata.get('data_publicacao')}")

if __name__ == "__main__":
    # Teste 1: Busca Semântica
    testar_busca("quais as regras de tarifas de energia em 2016?")
    
    # Teste 2: Busca por Assunto específico
    testar_busca("indenização de ativos de transmissão")
