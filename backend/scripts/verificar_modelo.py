import asyncio
from services.qdrant import get_qdrant_client
from llama_index.embeddings.openai import OpenAIEmbedding
import numpy as np

async def verificar_modelo_embedding():
    client = get_qdrant_client()
    embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    
    # 1. Pega um ponto e seu texto original
    point = client.scroll("aneel_pdfs", limit=1, with_vectors=True)[0][0]
    texto_original = point.payload.get("texto", "")
    vetor_no_banco = np.array(point.vector)
    
    # 2. Gera o vetor agora para o mesmo texto
    vetor_gerado_agora = np.array(embed_model.get_text_embedding(texto_original))
    
    # 3. Calcula similaridade de cosseno
    dot = np.dot(vetor_no_banco, vetor_gerado_agora)
    norm_a = np.linalg.norm(vetor_no_banco)
    norm_b = np.linalg.norm(vetor_gerado_agora)
    cosine_sim = dot / (norm_a * norm_b)
    
    print(f"\n--- VERIFICAÇÃO DE MODELO ---")
    print(f"Texto: {texto_original[:100]}...")
    print(f"Similaridade de Cosseno entre vetor do banco e novo embedding: {cosine_sim:.4f}")
    
    if cosine_sim < 0.9:
        print("\n[ALERTA] Os modelos NÃO coincidem! O banco foi indexado com outro modelo.")
    else:
        print("\n[OK] Os modelos coincidem.")

if __name__ == "__main__":
    asyncio.run(verificar_modelo_embedding())
