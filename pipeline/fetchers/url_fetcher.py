import io
import requests
from typing import Optional
from pipeline.base import BaseFetcher
from config import logger

class URLFetcher(BaseFetcher):
    """Buscador de arquivos via HTTP/HTTPS."""
    
    def __init__(self):
        self._session = requests.Session()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.aneel.gov.br/',
            'Connection': 'keep-alive',
        }

    def fetch(self, source: str) -> Optional[io.BytesIO]:
        """Source deve ser a URL completa."""
        try:
            response = self._session.get(source, headers=self._headers, timeout=30)
            response.raise_for_status()
            return io.BytesIO(response.content)
        except Exception as e:
            logger.error(f"Erro no URLFetcher para {source}: {e}")
            return None
