from typing import Tuple
from models import RetrievalMode
from pipeline.metadata_service import MetadataService
from pipeline.fetchers.gcs_fetcher import GCSFetcher
from pipeline.fetchers.url_fetcher import URLFetcher
from pipeline.fetchers.local_fetcher import LocalFetcher
from pipeline.parsers.pdf_parser import PyPDFParser
from config import logger

class DocumentPipeline:
    """Orquestrador do processamento de documentos: Metadados -> Fetch -> Parse."""
    
    def __init__(self):
        self._metadata_service = MetadataService()
        self._fetchers = {
            RetrievalMode.GCS: GCSFetcher(),
            RetrievalMode.URL: URLFetcher(),
            RetrievalMode.LOCAL: LocalFetcher()
        }
        self._default_parser = PyPDFParser()

    def process_document(self, registro_id: int, mode: RetrievalMode) -> Tuple[str, str]:
        """
        Executa o fluxo completo para um documento.
        Retorna: (texto_extraido, origem_amigavel)
        """
        # 1. Busca Metadados
        doc_info = self._metadata_service.get_best_pdf_info(registro_id)
        if not doc_info:
            return "", "Erro: Metadados não encontrados"

        # 2. Define Fonte e Fetcher
        fetcher = self._fetchers.get(mode)
        source = None
        origem_nome = "Desconhecida"

        if mode == RetrievalMode.GCS:
            source = doc_info.arquivo_nome
            origem_nome = "GCP Bucket"
        elif mode == RetrievalMode.URL:
            source = doc_info.url
            origem_nome = "URL Direta"
        elif mode == RetrievalMode.LOCAL:
            source = doc_info.arquivo_nome
            origem_nome = "PDF Local"

        if not source or not fetcher:
            logger.warning(f"Fonte ou Fetcher indisponível para ID {registro_id} no modo {mode}")
            return "", "Fallback (Ementa)"

        # 3. Download (Fetch)
        logger.info(f"Iniciando Fetch [{mode.value}]: {source}")
        file_stream = fetcher.fetch(source)
        if not file_stream:
            return "", f"Falha no Fetch ({origem_nome})"

        # 4. Extração (Parse)
        # Por enquanto simplificado: assume PDF. No futuro: roteador por extensão.
        text = self._default_parser.parse(file_stream)
        
        return text, origem_nome
