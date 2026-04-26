import os
import sqlite3
import json
import tiktoken
import re
import argparse
import multiprocessing as mp
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google.cloud import storage
from tqdm import tqdm
from backend.pipeline.parsers.pymupdf_parser import PyMuPDFParser

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------------------------
BASE_DIR         = Path(__file__).resolve().parent.parent  # Ajustado para backend/
DB_PATH          = BASE_DIR / "data" / "aneel_legislacao2.db"
PDFS_DIR         = BASE_DIR / "data" / "downloads"
OUTPUT_DIR       = BASE_DIR / "data" / "parsed_docs"
OUTPUT_PDFS_DIR  = OUTPUT_DIR / "pdfs"
OUTPUT_REG_DIR   = OUTPUT_DIR / "registros"

GCS_BUCKET_NAME  = os.environ.get("GCS_BUCKET_NAME")   # ex: "aneel-legislacao"
GCS_PREFIX_DOCS  = "parsed_docs"
GCS_PREFIX_BKP   = "backup/db_snapshots"

COLLECTION_REGISTROS = "aneel_registros"
COLLECTION_PDFS      = "aneel_pdfs"
EMBEDDING_MODEL      = "text-embedding-3-small"
VECTOR_SIZE          = 1536

CHUNK_SIZE           = 512    # tokens por chunk
CHUNK_OVERLAP        = 100    # overlap entre chunks adjacentes
EMBEDDING_BATCH_SIZE = 40     # máx 40 × 512 = ~280k tokens (limite: 300k)

tokenizer = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# UTILITÁRIOS
# ---------------------------------------------------------------------------

def call_with_retry(func, *args, retries=4, delay=2, **kwargs):
    """Retry com backoff exponencial. Levanta exceção após esgotar tentativas."""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (2 ** attempt))


def generate_deterministic_id(text: str) -> int:
    """ID numérico de 15 dígitos baseado em SHA256 — determinístico entre runs."""
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (10**15)


def normalizar_data_iso(data_str: str) -> str:
    if not data_str:
        return ""
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(data_str))
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"
    return str(data_str)


def get_db_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# ---------------------------------------------------------------------------
# GCS
# ---------------------------------------------------------------------------

def get_gcs_client() -> storage.Client:
    # Autentica via GOOGLE_APPLICATION_CREDENTIALS (arquivo JSON da service account)
    return storage.Client()


def upload_to_gcs(gcs_client: storage.Client, local_path: Path, gcs_path: str) -> None:
    """Faz upload de um arquivo local para o bucket GCS."""
    if not GCS_BUCKET_NAME:
        return
    bucket = gcs_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(str(local_path))


def backup_sqlite(gcs_client: storage.Client) -> None:
    """Faz upload do banco SQLite como snapshot com timestamp."""
    if not GCS_BUCKET_NAME:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = DB_PATH.stem
    gcs_path = f"{GCS_PREFIX_BKP}/{db_name}_{ts}.db"
    print(f"[*] Backup SQLite → gs://{GCS_BUCKET_NAME}/{gcs_path}")
    upload_to_gcs(gcs_client, DB_PATH, gcs_path)


# ---------------------------------------------------------------------------
# QDRANT
# ---------------------------------------------------------------------------

def garantir_collections_e_indexes(client: QdrantClient) -> None:
    """Cria collections e payload indexes se ainda não existirem."""
    for coll in [COLLECTION_REGISTROS, COLLECTION_PDFS]:
        if not client.collection_exists(coll):
            client.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE
                )
            )

    index_spec = [
        (COLLECTION_REGISTROS, "data_iso",     models.PayloadSchemaType.KEYWORD),
        (COLLECTION_REGISTROS, "situacao",     models.PayloadSchemaType.KEYWORD),
        (COLLECTION_PDFS,      "registro_id",  models.PayloadSchemaType.INTEGER),
        (COLLECTION_PDFS,      "pdf_nome",     models.PayloadSchemaType.KEYWORD),
        (COLLECTION_PDFS,      "data_iso",     models.PayloadSchemaType.KEYWORD),
        (COLLECTION_PDFS,      "natureza",     models.PayloadSchemaType.KEYWORD),
        (COLLECTION_PDFS,      "sigla",        models.PayloadSchemaType.KEYWORD),
    ]
    for collection, field, schema in index_spec:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=schema
            )
        except Exception:
            pass  # índice já existe


# ---------------------------------------------------------------------------
# WORKER — FASE 1 (roda em subprocessos)
# ---------------------------------------------------------------------------

def worker_processar_pdf(args: Tuple) -> Dict[str, Any]:
    p_row, pdfs_dir, out_dir, simple = args
    p_id, r_id, arquivo, natureza, sigla, url_origem, data_raw = p_row
    pdf_path = Path(pdfs_dir) / arquivo

    if not pdf_path.exists():
        return {"id": p_id, "status": "not_found", "arquivo": arquivo}

    path_md   = Path(out_dir) / f"{arquivo}.md"
    path_json = Path(out_dir) / f"{arquivo}.json"

    # Idempotência: se já foi parseado, retorna direto sem reprocessar
    if path_md.exists() and path_json.exists():
        try:
            with open(path_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return {
                "id": p_id, "status": "success", "arquivo": arquivo,
                "path_md": str(path_md), "path_json": str(path_json),
                "metadata": meta, "reused_cache": True
            }
        except Exception:
            pass  # JSON corrompido — faz o parse de novo

    try:
        parser = PyMuPDFParser()
        # Se simple=True, usa extração bruta rápida
        parsed = parser.parse(str(pdf_path), simple=simple)
        data_iso = normalizar_data_iso(data_raw)

        with open(path_md, "w", encoding="utf-8") as f:
            f.write(parsed["text"])

        meta = {
            "pdf_nome":            arquivo,
            "registro_id":         r_id,
            "sigla":               sigla,
            "natureza":            natureza,
            "url_origem":          url_origem,
            "data_iso":            data_iso,
            "links_referenciados": parsed["links_referenciados"],
            "modo_extracao":       "simples" if simple else "completo"
        }

        with open(path_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return {
            "id": p_id, "status": "success", "arquivo": arquivo,
            "path_md": str(path_md), "path_json": str(path_json),
            "metadata": meta, "reused_cache": False
        }
    except Exception as e:
        return {"id": p_id, "status": "error", "arquivo": arquivo, "error": str(e)}


# ---------------------------------------------------------------------------
# ORQUESTRADOR PRINCIPAL
# ---------------------------------------------------------------------------

def processar_ingestao(
    test_mode:   bool  = False,
    limit:       int   = 0,
    workers:     int   = 4,
    max_size_mb: float = 1.0,
    skip_backup: bool  = False,
):
    for d in [OUTPUT_DIR, OUTPUT_PDFS_DIR, OUTPUT_REG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    conn   = get_db_connection()
    cursor = conn.cursor()

    # Clientes externos (apenas fora do test_mode)
    client_openai = None
    client_qdrant = None
    client_gcs    = None

    if not test_mode:
        client_openai = OpenAI()
        client_qdrant = QdrantClient("http://localhost:6333")
        client_gcs    = get_gcs_client()
        garantir_collections_e_indexes(client_qdrant)

        # Backup do banco antes de começar
        if not skip_backup:
            backup_sqlite(client_gcs)

    # -------------------------------------------------------------------
    # ETAPA A — INDEXAR REGISTROS (granularidade macro)
    # -------------------------------------------------------------------
    if not test_mode:
        cursor.execute("""
            SELECT id, titulo, ementa, situacao, publicacao
            FROM registros
            WHERE status_ingestao = 'pendente'
        """)
        registros_rows = cursor.fetchall()
        if limit > 0:
            registros_rows = registros_rows[:limit]

        if registros_rows:
            print(f"[*] Etapa A: Indexando {len(registros_rows)} registros (macro)...")

            for i in tqdm(range(0, len(registros_rows), EMBEDDING_BATCH_SIZE), desc="Registros"):
                batch_regs = registros_rows[i : i + EMBEDDING_BATCH_SIZE]
                textos = [f"{r[1]}\n\n{r[2]}" for r in batch_regs]

                try:
                    response = call_with_retry(
                        client_openai.embeddings.create,
                        input=textos, model=EMBEDDING_MODEL
                    )
                    embeddings = [e.embedding for e in response.data]

                    points = [
                        models.PointStruct(
                            id=batch_regs[idx][0],
                            vector=embeddings[idx],
                            payload={
                                "registro_id": batch_regs[idx][0],
                                "titulo":      batch_regs[idx][1],
                                "ementa":      batch_regs[idx][2],
                                "situacao":    batch_regs[idx][3],
                                "data_iso":    normalizar_data_iso(batch_regs[idx][4]),
                            }
                        )
                        for idx in range(len(batch_regs))
                    ]
                    call_with_retry(
                        client_qdrant.upsert,
                        collection_name=COLLECTION_REGISTROS, points=points
                    )

                    # Salva snapshot local e sobe ao GCS
                    for reg in batch_regs:
                        reg_id = reg[0]
                        path_reg = OUTPUT_REG_DIR / f"registro_{reg_id}.json"
                        reg_data = {
                            "id": reg_id, "titulo": reg[1], "ementa": reg[2],
                            "situacao": reg[3], "data_iso": normalizar_data_iso(reg[4])
                        }
                        with open(path_reg, "w", encoding="utf-8") as f:
                            json.dump(reg_data, f, ensure_ascii=False, indent=2)

                        call_with_retry(
                            upload_to_gcs, client_gcs, path_reg,
                            f"{GCS_PREFIX_DOCS}/registros/registro_{reg_id}.json"
                        )
                        cursor.execute(
                            "UPDATE registros SET status_ingestao = 'indexado_qdrant' WHERE id = ?",
                            (reg_id,)
                        )
                    conn.commit()

                except Exception as e:
                    print(f"  [ERRO] Batch registros offset={i}: {e}")

    # -------------------------------------------------------------------
    # ETAPA B — FASE 1: PARSE PARALELO DE PDFS
    # -------------------------------------------------------------------
    cursor.execute("""
        SELECT p.id, p.registro_id, p.arquivo, p.natureza, p.sigla, p.url, r.publicacao
        FROM pdfs p
        JOIN registros r ON p.registro_id = r.id
        WHERE p.status_ingestao = 'pendente'
    """ if not test_mode else """
        SELECT p.id, p.registro_id, p.arquivo, p.natureza, p.sigla, p.url, r.publicacao
        FROM pdfs p
        JOIN registros r ON p.registro_id = r.id
    """)
    all_pdfs = cursor.fetchall()

    max_bytes = max_size_mb * 1024 * 1024
    pdfs_fila = [
        r for r in all_pdfs
        if r[2] and r[2].lower().endswith(".pdf")
        and (PDFS_DIR / r[2]).exists()
    ]
    if limit > 0:
        pdfs_fila = pdfs_fila[:limit]

    parsed_results = []
    if pdfs_fila:
        print(f"[*] Etapa B: Parse Paralelo ({workers} workers) → {len(pdfs_fila)} PDFs")
        args_list = []
        for row in pdfs_fila:
            pdf_path = PDFS_DIR / row[2]
            # Se o arquivo for maior que o limite, usa o modo simples
            simple_mode = pdf_path.stat().st_size > max_bytes
            args_list.append((row, str(PDFS_DIR), str(OUTPUT_PDFS_DIR), simple_mode))

        with mp.Pool(processes=workers) as pool:
            for res in tqdm(
                pool.imap_unordered(worker_processar_pdf, args_list),
                total=len(pdfs_fila), desc="Parsing"
            ):
                if res["status"] == "success":
                    parsed_results.append(res)
                elif res["status"] == "error" and not test_mode:
                    cursor.execute(
                        "UPDATE pdfs SET status_ingestao = 'erro' WHERE id = ?", (res["id"],)
                    )
                    conn.commit()

    # -------------------------------------------------------------------
    # ETAPA C — FASE 2: GCS UPLOAD + EMBEDDING + QDRANT
    # -------------------------------------------------------------------
    if not test_mode and parsed_results:
        print(f"[*] Etapa C: Upload GCS + Embeddings + Ingestão Qdrant → {len(parsed_results)} PDFs")

        for res in tqdm(parsed_results, desc="Ingestão"):
            try:
                # C1. Upload dos artefatos ao GCS (md + json)
                gcs_md_path   = f"{GCS_PREFIX_DOCS}/pdfs/{res['arquivo']}.md"
                gcs_json_path = f"{GCS_PREFIX_DOCS}/pdfs/{res['arquivo']}.json"

                call_with_retry(upload_to_gcs, client_gcs, Path(res["path_md"]),   gcs_md_path)
                call_with_retry(upload_to_gcs, client_gcs, Path(res["path_json"]), gcs_json_path)

                # C2. Chunking do texto completo
                with open(res["path_md"], "r", encoding="utf-8") as f:
                    full_text = f.read()

                tokens = tokenizer.encode(full_text)
                chunks = [
                    tokenizer.decode(tokens[i : i + CHUNK_SIZE])
                    for i in range(0, len(tokens), CHUNK_SIZE - CHUNK_OVERLAP)
                ]
                total_chunks = len(chunks)

                # C3. Batch embedding + upsert por lote de EMBEDDING_BATCH_SIZE
                pdf_ok = True
                for i in range(0, total_chunks, EMBEDDING_BATCH_SIZE):
                    batch = chunks[i : i + EMBEDDING_BATCH_SIZE]

                    response = call_with_retry(
                        client_openai.embeddings.create,
                        input=batch, model=EMBEDDING_MODEL
                    )
                    embeddings = [e.embedding for e in response.data]

                    points = [
                        models.PointStruct(
                            id=generate_deterministic_id(f"{res['arquivo']}_{i + idx}"),
                            vector=embeddings[idx],
                            payload={
                                **res["metadata"],
                                "texto":        batch[idx],
                                "chunk_index":  i + idx,
                                "total_chunks": total_chunks,
                                "gcs_md_path":  gcs_md_path,   # referência direta ao GCS
                            }
                        )
                        for idx in range(len(batch))
                    ]
                    call_with_retry(
                        client_qdrant.upsert,
                        collection_name=COLLECTION_PDFS, points=points
                    )

                # C4. Marca sucesso SOMENTE após todos os chunks confirmados
                if pdf_ok:
                    cursor.execute(
                        "UPDATE pdfs SET status_ingestao = 'indexado_qdrant' WHERE id = ?",
                        (res["id"],)
                    )
                    conn.commit()

            except Exception as e:
                print(f"  [ERRO PDF] {res['arquivo']}: {e}")
                cursor.execute(
                    "UPDATE pdfs SET status_ingestao = 'erro' WHERE id = ?", (res["id"],)
                )
                conn.commit()

    conn.close()
    print("[✓] Pipeline concluído.")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser_cli = argparse.ArgumentParser(description="Pipeline ANEEL — Ingestão Completa")
    parser_cli.add_argument(
        "--test-mode", action="store_true",
        help="Executa parse e salva localmente sem chamar OpenAI, Qdrant ou GCS."
    )
    parser_cli.add_argument(
        "--limit", type=int, default=0,
        help="Limita o número de documentos processados (0 = sem limite)."
    )
    parser_cli.add_argument(
        "--workers", type=int, default=4,
        help="Número de processos paralelos para parsing de PDFs."
    )
    parser_cli.add_argument(
        "--max-size", type=float, default=1.0,
        help="Tamanho máximo dos PDFs a processar, em MB (padrão: 1.0)."
    )
    parser_cli.add_argument(
        "--skip-backup", action="store_true",
        help="Pula o backup do SQLite no GCS (útil em runs incrementais frequentes)."
    )
    args = parser_cli.parse_args()

    processar_ingestao(
        test_mode=args.test_mode,
        limit=args.limit,
        workers=args.workers,
        max_size_mb=args.max_size,
        skip_backup=args.skip_backup,
    )
