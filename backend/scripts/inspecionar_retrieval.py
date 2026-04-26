import asyncio
from services.qdrant import get_registros_query_engine, get_pdfs_query_engine
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import Settings
from config import logger

async def inspecionar_retrieval():
    # TESTE COM ADA-002
    print("\n=== TESTANDO COM MODELO: text-embedding-ada-002 ===")
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-ada-002")

    query = "tarifas de energia"

    # 1. Testando Registros
    print("\n[REGISTROS]")
    engine_reg = get_registros_query_engine()
    retriever_reg = engine_reg.retriever
    nodes_reg = retriever_reg.retrieve(query)
    for i, node in enumerate(nodes_reg):
        print(f" Node {i+1} [Score: {node.score:.4f}]: {node.text[:200]}...")

    # 2. Testando PDFs
    print("\n[PDFS + GCS]")
    engine_pdf = get_pdfs_query_engine()
    retriever_pdf = engine_pdf.retriever
    nodes_pdf = retriever_pdf.retrieve(query)
    for i, node in enumerate(nodes_pdf):
        print(f" Node {i+1} [Score: {node.score:.4f}]: {node.text[:200]}...")

if __name__ == "__main__":
    asyncio.run(inspecionar_retrieval())
