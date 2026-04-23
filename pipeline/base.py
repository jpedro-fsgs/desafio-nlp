import abc
import io
from typing import Optional

class BaseFetcher(abc.ABC):
    """Interface abstrata para buscadores de arquivos (Bytes)."""
    @abc.abstractmethod
    def fetch(self, source: str) -> Optional[io.BytesIO]:
        pass

class BaseParser(abc.ABC):
    """Interface abstrata para conversores de Bytes em Texto."""
    @abc.abstractmethod
    def parse(self, file_stream: io.BytesIO, max_chars: int = 50000) -> str:
        pass
