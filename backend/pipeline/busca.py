import os
import json
from pathlib import Path
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google.cloud import storage

COLLECTION_REGISTROS = "aneel_registros"
COLLECTION_PDFS      = "aneel_pdfs"
EMBEDDING_MODEL      = "text-embedding-3-small"
GCS_BUCKET_NAME      = os.environ.get("GCS_BUCKET_NAME")


def buscar(
    query:      str,
    top_k:      int  = 5,
    filtros:    dict = None,   # ex: {"natureza": "Resolução Normativa", "data_iso": "2020"}
    usar_macro: bool = False,  # True = busca em registros; False = busca em chunks
) -> list[dict]:
    """
    Retorna documentos completos (do GCS) ranqueados por similaridade semântica.

    Parâmetros:
        query      — Pergunta ou texto de busca
        top_k      — Quantos documentos distintos retornar
        filtros    — Filtros de metadados (aplicados antes do ranqueamento vetorial)
        usar_macro — Se True, busca na collection de registros (nível macro)
    """
    openai  = OpenAI()
    qdrant  = QdrantClient("http://localhost:6333")
    gcs     = storage.Client()
    bucket  = None
    if GCS_BUCKET_NAME:
        bucket = gcs.bucket(GCS_BUCKET_NAME)

    # 1. Embeda a query
    q_emb = openai.embeddings.create(
        input=[query], model=EMBEDDING_MODEL
    ).data[0].embedding

    # 2. Monta filtro Qdrant (opcional)
    qdrant_filter = None
    if filtros:
        conditions = []
        for campo, valor in filtros.items():
            conditions.append(
                models.FieldCondition(
                    key=campo,
                    match=models.MatchValue(value=valor)
                )
            )
        qdrant_filter = models.Filter(must=conditions)

    # 3. Busca semântica nos chunks
    collection = COLLECTION_REGISTROS if usar_macro else COLLECTION_PDFS
    hits = qdrant.search(
        collection_name=collection,
        query_vector=q_emb,
        query_filter=qdrant_filter,
        limit=top_k * 3,          # busca mais para deduplicar por documento
        with_payload=True,
    )

    # 4. Deduplica por documento e recupera texto completo do GCS
    vistos   = set()
    result   = []

    for hit in hits:
        # Identificador único do documento
        doc_id = hit.payload.get("pdf_nome") or str(hit.payload.get("registro_id"))
        
        if doc_id in vistos:
            continue
        vistos.add(doc_id)

        # Busca o documento completo no GCS
        gcs_md_path = hit.payload.get("gcs_md_path")
        texto_completo = None
        if gcs_md_path and bucket:
            try:
                blob = bucket.blob(gcs_md_path)
                texto_completo = blob.download_as_text(encoding="utf-8")
            except Exception as e:
                print(f"Erro ao baixar do GCS: {e}")

        result.append({
            "score":           hit.score,
            "metadata":        hit.payload,
            "texto_completo":  texto_completo,  # documento inteiro para o LLM
            "chunk_relevante": hit.payload.get("texto"),  # trecho que gerou o match
        })

        if len(result) >= top_k:
            break

    return result
