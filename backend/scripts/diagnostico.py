import asyncio
from services.qdrant import get_qdrant_client, get_registros_query_engine, get_pdfs_query_engine
from services.gcs import fetch_markdown_from_gcs
from config import COLLECTION_REGISTROS, COLLECTION_PDFS, logger

async def diagnostico_completo():
    client = get_qdrant_client()
    
    print("\n=== 1. VERIFICANDO COLEÇÕES NO QDRANT ===")
    try:
        collections = client.get_collections().collections
        names = [c.name for c in collections]
        print(f"Coleções encontradas: {names}")
        
        for coll in [COLLECTION_REGISTROS, COLLECTION_PDFS]:
            if coll in names:
                info = client.get_collection(coll)
                print(f" - {coll}: {info.points_count} pontos encontrados.")
            else:
                print(f" - [ERRO] Coleção {coll} não encontrada!")
    except Exception as e:
        print(f"Erro ao acessar Qdrant: {e}")

    print("\n=== 2. TESTANDO BUSCA DE REGISTROS (EMENTAS) ===")
    try:
        engine = get_registros_query_engine()
        resp = await engine.aquery("tarifas de energia")
        print(f"Resposta (Registros): {str(resp)[:300]}...")
    except Exception as e:
        print(f"Erro na busca de registros: {e}")

    print("\n=== 3. TESTANDO BUSCA DE PDFS (CONTENT + GCS) ===")
    try:
        engine = get_pdfs_query_engine()
        resp = await engine.aquery("detalhes técnicos de transmissão")
        print(f"Resposta (PDFs): {str(resp)[:300]}...")
    except Exception as e:
        print(f"Erro na busca de PDFs: {e}")

    print("\n=== 4. TESTANDO ACESSO AO GCS ===")
    try:
        # Tenta ler um arquivo genérico se houver pontos em aneel_pdfs
        points = client.scroll(COLLECTION_PDFS, limit=1)[0]
        if points:
            pdf_nome = points[0].payload.get("pdf_nome")
            if pdf_nome:
                print(f"Tentando ler Markdown para: {pdf_nome}")
                content = fetch_markdown_from_gcs(pdf_nome)
                if content:
                    print(f"Sucesso! GCS retornou {len(content)} caracteres.")
                else:
                    print(f"Falha: GCS retornou VAZIO para {pdf_nome}")
            else:
                print("Não foi possível extrair pdf_nome do payload.")
        else:
            print("Nenhum ponto na coleção de PDFs para testar GCS.")
    except Exception as e:
        print(f"Erro no teste de GCS: {e}")

if __name__ == "__main__":
    asyncio.run(diagnostico_completo())
