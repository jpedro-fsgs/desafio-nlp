import os
import sqlite3
import requests
import io
import random
import time
from typing import Optional, Tuple
from pypdf import PdfReader
from config import DB_PATH, DOWNLOADS_DIR, logger

# Sessão global para persistir cookies (importante para Cloudflare)
_session = requests.Session()

def get_best_pdf_info(registro_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Busca o melhor arquivo PDF (caminho local e URL) para um registro_id no SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT arquivo, url FROM pdfs 
            WHERE registro_id = ? 
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
    """Baixa um PDF via URL com persistência de sessão e extrai o texto."""
    if not url:
        return ""
    
    # Headers que mimetizam perfeitamente um navegador moderno
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.aneel.gov.br/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }

    try:
        # Se for o primeiro request da sessão, visita a home para pegar o cookie inicial
        if not _session.cookies:
            _session.get("https://www.aneel.gov.br/", headers=headers, timeout=15)
            time.sleep(random.uniform(1.0, 2.0))

        response = _session.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        with io.BytesIO(response.content) as f:
            reader = PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                if len(text) > max_chars:
                    break
        logger.info(f"Texto extraído via URL: {url.split('/')[-1]}")
        return text[:max_chars]
    except Exception as e:
        logger.error(f"Erro ao extrair PDF da URL {url}: {e}")
        return ""
