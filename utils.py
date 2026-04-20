import os
import sqlite3
from typing import Optional
from pypdf import PdfReader
from config import DB_PATH, DOWNLOADS_DIR, logger

def get_best_pdf_path(registro_id: int) -> Optional[str]:
    """Busca o melhor arquivo PDF para um registro_id no SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Prioriza 'Texto Integral', depois 'Voto', depois qualquer outro
        cursor.execute("""
            SELECT arquivo FROM pdfs 
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
        
        if row and row[0]:
            file_path = os.path.join(DOWNLOADS_DIR, row[0])
            if os.path.exists(file_path):
                return file_path
    except Exception as e:
        logger.error(f"Erro SQLite (Registro ID {registro_id}): {e}")
    return None

def extract_text_from_pdf(pdf_path: str, max_chars: int = 50000) -> str:
    """Extrai texto de um PDF usando pypdf."""
    print(f"Extraindo texto do PDF: {pdf_path}")
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            if len(text) > max_chars:
                break
        logger.info(f"Texto extraído do PDF: {os.path.basename(pdf_path)} ({len(text)} caracteres)")
    except Exception as e:
        logger.error(f"Erro ao ler PDF {pdf_path}: {e}")
    return text[:max_chars]
