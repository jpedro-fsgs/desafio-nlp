import io
from pypdf import PdfReader
from pipeline.base import BaseParser
from config import logger

class PyPDFParser(BaseParser):
    """Conversor de PDF para Texto usando a biblioteca pypdf."""
    
    def parse(self, file_stream: io.BytesIO, max_chars: int = 50000) -> str:
        text = ""
        try:
            # Garante que o ponteiro está no início
            file_stream.seek(0)
            reader = PdfReader(file_stream)
            
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                
                if len(text) > max_chars:
                    break
                    
            return text[:max_chars]
        except Exception as e:
            logger.error(f"Erro ao parsear PDF: {e}")
            return ""
