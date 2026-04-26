import io
import re
from typing import List, Dict, Any, Optional
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from llama_index.core import Document
from ..base import BaseParser

class DoclingParser(BaseParser):
    """
    Parser universal utilizando Docling para extração de Markdown, Tabelas e Metadados.
    Suporta PDF, XLSX e CSV.
    """
    def __init__(self):
        # Detecta o melhor acelerador disponível (GPU > CPU)
        import torch
        from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
        
        device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.CPU
        
        # Opções de pipeline otimizadas para performance máxima
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True 
        pipeline_options.do_table_structure = True
        pipeline_options.generate_page_images = False
        
        # Configura as opções do acelerador
        pipeline_options.accelerator_options = AcceleratorOptions(
            device=device,
            num_threads=4 # Otimiza uso de threads em conjunto com GPU
        )
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def parse(self, file_stream: io.BytesIO, max_chars: int = 1000000) -> str:
        """Implementação simplificada para satisfazer a interface BaseParser."""
        results = self.parse_rich(file_stream, "unknown_doc")
        if results:
            return results[0].text[:max_chars]
        return ""

    def parse_rich(self, file_stream: io.BytesIO, file_name: str) -> List[Document]:
        """
        Retorna uma lista de LlamaIndex Documents com Markdown e metadados enriquecidos.
        """
        from docling_core.types.io import DocumentStream
        
        file_stream.seek(0)
        source = DocumentStream(name=file_name, stream=file_stream)
        
        try:
            conversion_result = self.converter.convert(source)
            doc = conversion_result.document
            
            # 1. Exporta conteúdo para Markdown (Preserva tabelas e hierarquia)
            markdown_content = doc.export_to_markdown()
            
            # 2. Extrai metadados estruturais
            metadata = {
                "file_name": file_name,
                "title": self._extract_title(doc),
                "has_tables": len(doc.tables) > 0,
                "all_hyperlinks": self._extract_links(doc),
                "revocation_links": self._extract_revocations(doc),
                "doc_type": "PDF" if file_name.lower().endswith(".pdf") else "SPREADSHEET"
            }
            
            return [Document(text=markdown_content, metadata=metadata)]
            
        except Exception as e:
            # Em caso de erro no Docling, logamos e retornamos lista vazia
            print(f"Erro ao processar {file_name} com Docling: {e}")
            return []

    def _extract_title(self, doc) -> str:
        """Tenta encontrar o título principal no layout do documento."""
        for element in doc.elements:
            if getattr(element, "label", "") in ["title", "heading_1"]:
                return element.text
        return "Sem título identificado"

    def _extract_links(self, doc) -> List[str]:
        """Coleta todos os links únicos presentes no documento."""
        links = set()
        for element in doc.elements:
            # Docling armazena links em atributos específicos dependendo do elemento
            if hasattr(element, "links") and element.links:
                for link in element.links:
                    if link.url:
                        links.add(link.url)
        return list(links)

    def _extract_revocations(self, doc) -> List[Dict[str, str]]:
        """
        Analisa links em busca de contexto de revogação ou alteração de normas.
        """
        revocations = []
        # Palavras-chave que indicam relação normativa
        keywords = ["revog", "alter", "substitu", "vigo", "complement"]
        
        for element in doc.elements:
            text = element.text.lower()
            if any(k in text for k in keywords):
                if hasattr(element, "links") and element.links:
                    for link in element.links:
                        revocations.append({
                            "link": link.url,
                            "context": element.text[:300] # Salva o parágrafo de contexto
                        })
        return revocations
