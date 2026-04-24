import io
import os
from typing import Optional
from pipeline.base import BaseFetcher
from config import DOWNLOADS_DIR, logger

class LocalFetcher(BaseFetcher):
    """Buscador de arquivos no disco local."""
    
    def fetch(self, source: str) -> Optional[io.BytesIO]:
        """Source deve ser o caminho relativo ou absoluto do arquivo."""
        try:
            # Se source for apenas o nome do arquivo, completa com DOWNLOADS_DIR
            path = source if os.path.isabs(source) else os.path.join(DOWNLOADS_DIR, source)
            
            if not os.path.exists(path):
                logger.warning(f"Arquivo não encontrado localmente: {path}")
                return None

            with open(path, "rb") as f:
                return io.BytesIO(f.read())
        except Exception as e:
            logger.error(f"Erro no LocalFetcher para {source}: {e}")
            return None
