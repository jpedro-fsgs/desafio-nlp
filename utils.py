import os
import sqlite3
import requests
import io
import random
from typing import Optional, Tuple
from pypdf import PdfReader
from config import DB_PATH, DOWNLOADS_DIR, GCS_BUCKET_NAME, logger

# Cliente GCS inicializado sob demanda (Lazy loading)
_storage_client = None
_bucket = None

def _get_gcs_bucket():
    global _storage_client, _bucket
    if _bucket is None:
        try:
            from google.cloud import storage
            _storage_client = storage.Client()
            _bucket = _storage_client.bucket(GCS_BUCKET_NAME)
        except Exception as e:
            logger.error(f"Erro ao inicializar cliente GCS: {e}")
            raise e
    return _bucket

def get_best_pdf_info(registro_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Busca o melhor arquivo PDF (caminho local e URL) para um registro_id no SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Filtra apenas PDFs
        cursor.execute("""
            SELECT arquivo, url FROM pdfs 
            WHERE registro_id = ? AND (arquivo LIKE '%.pdf' OR url LIKE '%.pdf%')
            ORDER BY CASE 
                WHEN tipo = 'Texto Integral' THEN 1 
                WHEN tipo = 'Voto' THEN 2 
                ELSE 3 
            END 
            LIMIT 1
        """, (registro_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            arquivo, url = row
            file_path = os.path.join(DOWNLOADS_DIR, arquivo) if arquivo else None
            return file_path, url
    except Exception as e:
        logger.error(f"Erro SQLite (Registro ID {registro_id}): {e}")
    return None, None

def extract_text_from_pdf(pdf_path: str, max_chars: int = 50000) -> str:
    """Extrai texto de um PDF local usando pypdf."""
    if not pdf_path or not os.path.exists(pdf_path):
        return ""
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            if len(text) > max_chars:
                break
        logger.info(f"Texto extraído do PDF local: {os.path.basename(pdf_path)}")
    except Exception as e:
        logger.error(f"Erro ao ler PDF local {pdf_path}: {e}")
    return text[:max_chars]

def extract_text_from_url(url: str, max_chars: int = 50000) -> str:
    """Baixa um PDF via URL com headers adequados e extrai o texto em memória."""
    if not url:
        return ""
    text = ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.aneel.gov.br/',
            'Connection': 'keep-alive',
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        with io.BytesIO(response.content) as f:
            reader = PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                if len(text) > max_chars:
                    break
        logger.info(f"Texto extraído via URL: {url.split('/')[-1]}")
    except Exception as e:
        logger.error(f"Erro ao extrair PDF da URL {url}: {e}")
    return text[:max_chars]

def extract_text_from_gcs(nome_arquivo: str, max_chars: int = 50000) -> str:
    """Baixa o PDF do GCP Bucket para a memória e extrai o texto."""
    if not nome_arquivo:
        return ""
    text = ""
    try:
        bucket = _get_gcs_bucket()
        blob = bucket.blob(nome_arquivo)
        
        if not blob.exists():
            logger.warning(f"Arquivo não encontrado no GCS: {nome_arquivo}")
            return ""

        pdf_bytes = blob.download_as_bytes()
        
        with io.BytesIO(pdf_bytes) as f:
            reader = PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                if len(text) > max_chars:
                    break
                    
        logger.info(f"Texto extraído do GCS: {nome_arquivo}")
        return text[:max_chars]
        
    except Exception as e:
        logger.error(f"Erro ao ler PDF do GCS {nome_arquivo}: {e}")
        return ""
