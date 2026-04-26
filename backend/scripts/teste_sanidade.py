import asyncio
from services.qdrant import get_registros_query_engine
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
import config

async def teste_sanidade():
    # Garante configuração oficial
    config.setup_llama_index()
    
    # Query baseada em um registro que confirmamos existir no Qdrant via scroll
    query = "Oliveira Energia Geração e Serviços Ltda Amazonas"
    
    print(f"\n--- TESTE DE SANIDADE (Query Real): {query} ---")
    
    engine = get_registros_query_engine()
    retriever = engine.retriever
    nodes = retriever.retrieve(query)
    
    if not nodes:
        print("Nenhum resultado encontrado.")
        return

    for i, node in enumerate(nodes):
        print(f"Resultado {i+1}:")
        print(f" - Score: {node.score:.4f}")
        print(f" - Texto: {node.text[:150]}...")
        print(f" - Metadados: {node.metadata}")

if __name__ == "__main__":
    asyncio.run(teste_sanidade())
