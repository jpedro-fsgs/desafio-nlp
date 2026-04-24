import sqlite3
from dataclasses import dataclass
from typing import Optional
from config import DB_PATH, logger

@dataclass
class DocumentInfo:
    registro_id: int
    arquivo_nome: Optional[str] = None
    url: Optional[str] = None

class MetadataService:
    """Serviço responsável por buscar informações de documentos no SQLite."""
    
    @staticmethod
    def get_best_pdf_info(registro_id: int) -> Optional[DocumentInfo]:
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
                arquivo_nome, url = row
                return DocumentInfo(
                    registro_id=registro_id,
                    arquivo_nome=arquivo_nome,
                    url=url
                )
        except Exception as e:
            logger.error(f"Erro no MetadataService (ID {registro_id}): {e}")
        
        return None
