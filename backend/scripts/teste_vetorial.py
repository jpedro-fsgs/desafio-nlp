import asyncio
from services.qdrant import get_qdrant_client
from llama_index.embeddings.openai import OpenAIEmbedding
from config import COLLECTION_PDFS, COLLECTION_REGISTROS

async def testar_raw_search():
    client = get_qdrant_client()
    embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    
    query = "tarifas de energia"
    query_vector = embed_model.get_query_embedding(query)
    
    print(f"\n--- BUSCA VETORIAL PURA: {query} ---")
    
    for coll in [COLLECTION_REGISTROS, COLLECTION_PDFS]:
        results = client.search(
            collection_name=coll,
            query_vector=query_vector,
            limit=3
        )
        print(f"\nColeção: {coll}")
        for res in results:
            text = res.payload.get("ementa") or res.payload.get("texto")
            print(f" [Score: {res.score:.4f}] {str(text)[:150]}...")

if __name__ == "__main__":
    asyncio.run(testar_raw_search())
