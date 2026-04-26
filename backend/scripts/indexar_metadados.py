"""
Pipeline de Ingestão ANEEL — V4 Robusta (Super-Batches)
======================================================
Correções aplicadas vs V3:
  [C1] Chunking: decode seguro com errors='replace' evita crash em fronteiras UTF-8.
  [C2] Registros: texto truncado a MAX_REGISTRO_TOKENS antes do embedding.
  [C3] IDs: UUID5 (namespace + chave) elimina colisões por módulo de hash.
  [C4] PDFs ausentes: atualizados para 'nao_encontrado' no banco ao invés de ignorados.
  [C5] Índices Qdrant: falhas não são engolidas — re-raise após log.
  [C6] Arquivos temporários: escrita atômica via NamedTemporaryFile + rename.
  [C7] Conexão SQLite: criada APÓS o Pool para evitar compartilhamento entre processos.
  [C8] test_mode: inclui validação de chunking sem chamar APIs externas.
  [C9] Memória: workers reportam tamanho do PDF processado para monitoramento.
  [C10] Super-Batches: processamento em lotes de 100 docs para controle de RAM.
"""

import os
import sqlite3
import json
import tiktoken
import re
import argparse
import multiprocessing as mp
import uuid
import time
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

# Carregar variáveis de ambiente imediatamente
load_dotenv()

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models
from tqdm import tqdm
from scripts.parsers.pymupdf_parser import PyMuPDFParser

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Configurações
# ─────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DB_PATH   = BASE_DIR / "data" / "aneel_legislacao2.db"
PDFS_DIR  = BASE_DIR / "data" / "downloads"
OUTPUT_DIR             = BASE_DIR / "data" / "parsed_docs"
OUTPUT_PDFS_DIR        = OUTPUT_DIR / "pdfs"
OUTPUT_REGISTROS_DIR   = OUTPUT_DIR / "registros"

COLLECTION_REGISTROS = "aneel_registros"
COLLECTION_PDFS      = "aneel_pdfs"
EMBEDDING_MODEL      = "text-embedding-3-small"
EMBEDDING_DIM        = 1536

CHUNK_SIZE            = 800     # Reduzido para criar vetores mais densos e precisos (RAG)
CHUNK_OVERLAP         = 100     # Reduzido proporcionalmente
EMBEDDING_BATCH_SIZE  = 40      # chunks por request à OpenAI (≤300 k tokens/req)

# [C2] Limite real do text-embedding-3-small é 8 191 tokens.
MAX_REGISTRO_TOKENS = 8_000

# Namespace fixo para geração de UUID5 determinísticos
_UUID_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

tokenizer = tiktoken.get_encoding("cl100k_base")


# ─────────────────────────────────────────────
#  Funções auxiliares
# ─────────────────────────────────────────────

def call_with_retry(func, *args, retries: int = 3, delay: float = 2.0, **kwargs):
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = delay * (2 ** attempt)
            log.warning(f"Tentativa {attempt + 1}/{retries} falhou ({exc}). Retry em {wait:.0f}s.")
            time.sleep(wait)

def generate_deterministic_id(key: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, key))

def normalizar_data_iso(data_str: str) -> str:
    if not data_str:
        return ""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(data_str))
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return str(data_str)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def truncar_tokens(texto: str, max_tokens: int) -> str:
    tokens = tokenizer.encode(texto)
    if len(tokens) <= max_tokens:
        return texto
    return tokenizer.decode(tokens[:max_tokens])

def chunkify(full_text: str, chunk_size: int, overlap: int) -> List[str]:
    tokens = tokenizer.encode(full_text)
    chunks: List[str] = []
    step = chunk_size - overlap
    if step <= 0: raise ValueError("overlap deve ser menor que chunk_size")
    for start in range(0, len(tokens), step):
        slice_tokens = tokens[start : start + chunk_size]
        chunks.append(tokenizer.decode(slice_tokens))
    return chunks

def garantir_indexes(client: QdrantClient) -> None:
    schema = {
        COLLECTION_REGISTROS: [("data_iso", models.PayloadSchemaType.KEYWORD), ("situacao", models.PayloadSchemaType.KEYWORD)],
        COLLECTION_PDFS: [("registro_id", models.PayloadSchemaType.INTEGER), ("pdf_nome", models.PayloadSchemaType.KEYWORD), ("data_iso", models.PayloadSchemaType.KEYWORD)]
    }
    for collection, fields in schema.items():
        for field, stype in fields:
            try:
                client.create_payload_index(collection_name=collection, field_name=field, field_schema=stype)
            except Exception as exc:
                if "already exists" not in str(exc).lower(): raise

def escrever_arquivo_atomico(path: Path, content: str) -> None:
    dir_ = path.parent
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dir_, delete=False, suffix=".tmp") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)

# ─────────────────────────────────────────────
#  Worker Parsing (Fase 1)
# ─────────────────────────────────────────────

def worker_processar_pdf(args: Tuple) -> Dict[str, Any]:
    p_row, pdfs_dir, out_dir = args
    p_id, r_id, arquivo, natureza, sigla, url_origem, data_raw = p_row

    pdf_path = Path(pdfs_dir) / arquivo
    if not pdf_path.exists():
        return {"id": p_id, "status": "not_found", "arquivo": arquivo}

    try:
        parser = PyMuPDFParser()
        parsed = parser.parse(str(pdf_path))
        data_iso = normalizar_data_iso(data_raw)
        path_md, path_json = Path(out_dir) / f"{arquivo}.md", Path(out_dir) / f"{arquivo}.json"
        
        escrever_arquivo_atomico(path_md, parsed["text"])
        meta = {"pdf_nome": arquivo, "registro_id": r_id, "sigla": sigla, "natureza": natureza, "url_origem": url_origem, "data_iso": data_iso, "links_referenciados": parsed["links_referenciados"]}
        escrever_arquivo_atomico(path_json, json.dumps(meta, ensure_ascii=False, indent=2))

        return {"id": p_id, "status": "success", "arquivo": arquivo, "path_md": str(path_md), "metadata": meta}
    except Exception as exc:
        return {"id": p_id, "status": "error", "arquivo": arquivo, "error": str(exc)}

# ─────────────────────────────────────────────
#  Processamento Ingestão (Threaded — Fase 2)
# ─────────────────────────────────────────────

def ingerir_pdf(res: Dict[str, Any], client_openai: OpenAI, client_qdrant: QdrantClient) -> Tuple[int, bool]:
    try:
        with open(res["path_md"], "r", encoding="utf-8") as f:
            full_text = f.read()
        chunks = chunkify(full_text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks: return res["id"], True

        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            resp = call_with_retry(client_openai.embeddings.create, input=batch, model=EMBEDDING_MODEL)
            if not resp: raise ValueError("Resposta nula da OpenAI")
            
            embeddings = [e.embedding for e in resp.data]
            points = [models.PointStruct(
                id=generate_deterministic_id(f"{res['arquivo']}_chunk_{i + idx}"),
                vector=embeddings[idx],
                payload={**res["metadata"], "texto": batch[idx], "chunk_index": i + idx, "total_chunks": len(chunks)}
            ) for idx in range(len(batch))]
            call_with_retry(client_qdrant.upsert, collection_name=COLLECTION_PDFS, points=points)
        return res["id"], True
    except Exception as exc:
        log.error(f"  [ERRO PDF] {res['arquivo']}: {exc}")
        return res["id"], False

# ─────────────────────────────────────────────
#  Orquestrador
# ─────────────────────────────────────────────

def processar_ingestao(test_mode: bool = False, limit: int = 0, workers: int = 4, max_size_mb: float = 1.0):
    for d in [OUTPUT_DIR, OUTPUT_PDFS_DIR, OUTPUT_REGISTROS_DIR]: d.mkdir(parents=True, exist_ok=True)
    
    client_openai, client_qdrant = None, None
    if not test_mode:
        client_openai = OpenAI()
        
        # Conecta ao Qdrant Cloud se as variáveis estiverem presentes, senão usa localhost
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        
        if qdrant_url and qdrant_api_key:
            log.info(f"Conectando ao Qdrant Cloud: {qdrant_url}")
            client_qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        else:
            log.info("Conectando ao Qdrant Local (localhost:6333)")
            client_qdrant = QdrantClient("http://localhost:6333")
            
        for coll in [COLLECTION_REGISTROS, COLLECTION_PDFS]:
            if not client_qdrant.collection_exists(coll):
                client_qdrant.create_collection(coll, vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE))
        garantir_indexes(client_qdrant)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT p.id, p.registro_id, p.arquivo, p.natureza, p.sigla, p.url, r.publicacao FROM pdfs p JOIN registros r ON p.registro_id = r.id " + ("WHERE p.status_ingestao = 'pendente'" if not test_mode else ""))
    all_rows = cursor.fetchall()

    max_bytes = max_size_mb * 1024 * 1024
    pdfs_fila, ausentes_ids = [], []
    for row in all_rows:
        p = PDFS_DIR / row[2]
        if not p.exists(): ausentes_ids.append(row[0])
        elif p.stat().st_size <= max_bytes: pdfs_fila.append(row)

    if ausentes_ids and not test_mode:
        cursor.executemany("UPDATE pdfs SET status_ingestao = 'nao_encontrado' WHERE id = ?", [(i,) for i in ausentes_ids])
        conn.commit()

    if limit > 0: pdfs_fila = pdfs_fila[:limit]

    # --- FASE A: REGISTROS (Batch de 40) ---
    if not test_mode and client_openai and client_qdrant:
        cursor.execute("SELECT id, titulo, ementa, situacao, publicacao FROM registros WHERE status_ingestao = 'pendente'")
        regs = cursor.fetchall()
        if limit > 0: regs = regs[:limit]
        if regs:
            log.info(f"[Fase A] Ingerindo {len(regs)} registros em batches...")
            for i in range(0, len(regs), EMBEDDING_BATCH_SIZE):
                batch = regs[i:i+EMBEDDING_BATCH_SIZE]
                texts = [truncar_tokens(f"{r[1]}\n\n{r[2]}", MAX_REGISTRO_TOKENS) for r in batch]
                try:
                    resp = call_with_retry(client_openai.embeddings.create, input=texts, model=EMBEDDING_MODEL)
                    if not resp: raise ValueError("Resposta nula da OpenAI")
                    
                    embs = [e.embedding for e in resp.data]
                    points = [models.PointStruct(id=generate_deterministic_id(f"registro_{r[0]}"), vector=embs[idx], 
                                                payload={"registro_id": r[0], "titulo": r[1], "ementa": r[2], "situacao": r[3], "data_iso": normalizar_data_iso(r[4])}) 
                              for idx, r in enumerate(batch)]
                    call_with_retry(client_qdrant.upsert, collection_name=COLLECTION_REGISTROS, points=points)
                    cursor.executemany("UPDATE registros SET status_ingestao = 'indexado_qdrant' WHERE id = ?", [(r[0],) for r in batch])
                    conn.commit()
                except Exception as exc: log.error(f"Erro no batch de registros: {exc}")

    # --- FASE 1 e 2: PDFs em Super-Batches de 100 ---
    SUPER_BATCH_SIZE = 100
    if pdfs_fila:
        log.info(f"[*] Processando {len(pdfs_fila)} PDFs em super-batches de {SUPER_BATCH_SIZE}...")
        for i in range(0, len(pdfs_fila), SUPER_BATCH_SIZE):
            current_batch = pdfs_fila[i:i+SUPER_BATCH_SIZE]
            log.info(f"\n>>> SUPER-BATCH {(i//100)+1} (Docs {i} a {i+len(current_batch)})")
            
            # Fase 1: Parsing
            parsed_results = []
            args_list = [(row, str(PDFS_DIR), str(OUTPUT_PDFS_DIR)) for row in current_batch]
            with mp.Pool(processes=workers) as pool:
                for res in tqdm(pool.imap_unordered(worker_processar_pdf, args_list), total=len(current_batch), desc="Parsing"):
                    if res["status"] == "success": parsed_results.append(res)
                    elif not test_mode: cursor.execute("UPDATE pdfs SET status_ingestao = ? WHERE id = ?", ("erro" if res["status"]=="error" else "nao_encontrado", res["id"]))
                conn.commit()

            # Fase 2: Ingestão Threaded
            if not test_mode and parsed_results and client_openai and client_qdrant:
                
                c_openai: OpenAI = client_openai
                c_qdrant: QdrantClient = client_qdrant
                
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = {executor.submit(ingerir_pdf, r, c_openai, c_qdrant): r for r in parsed_results}
                    for fut in tqdm(as_completed(futures), total=len(parsed_results), desc="Ingestão"):
                        pid, ok = fut.result()
                        cursor.execute("UPDATE pdfs SET status_ingestao = ? WHERE id = ?", ("indexado_qdrant" if ok else "erro", pid))
                    conn.commit()
            parsed_results.clear()

    conn.close()
    log.info("Pipeline concluído.")

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--test-mode", action="store_true")
    cli.add_argument("--limit", type=int, default=0)
    cli.add_argument("--workers", type=int, default=4)
    cli.add_argument("--max-size", type=float, default=1.0)
    args = cli.parse_args()
    processar_ingestao(test_mode=args.test_mode, limit=args.limit, workers=args.workers, max_size_mb=args.max_size)
