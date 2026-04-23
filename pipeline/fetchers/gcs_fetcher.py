import io
from typing import Optional
from google.cloud import storage
from pipeline.base import BaseFetcher
from config import GCS_BUCKET_NAME, logger


class GCSFetcher(BaseFetcher):
    """Buscador de arquivos no Google Cloud Storage."""
    
    def __init__(self):
        self._client = None
        self._bucket = None

    def _initialize(self):
        if self._bucket is None:
            try:
                self._client = storage.Client()
                self._bucket = self._client.bucket(GCS_BUCKET_NAME)
            except Exception as e:
                logger.error(f"Erro ao inicializar cliente GCS: {e}")
                raise e

    def fetch(self, source: str) -> Optional[io.BytesIO]:
        """Source deve ser o nome do objeto no bucket."""
        try:
            self._initialize()
            if self._bucket is None:
                logger.error("Bucket não inicializado corretamente.")
                return None
                
            blob = self._bucket.blob(source)
            
            if not blob.exists():
                logger.warning(f"Objeto não encontrado no GCS: {source}")
                return None

            content = blob.download_as_bytes()
            return io.BytesIO(content)
        except Exception as e:
            logger.error(f"Erro no GCSFetcher para {source}: {e}")
            return None
