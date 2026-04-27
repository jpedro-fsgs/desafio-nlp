import os
from datetime import datetime, timedelta
from typing import List, Optional
from google.cloud import storage
from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from config import GCS_BUCKET_NAME, logger, COLLECTION_PDFS

DEBUG_FILE = "debug_retrieval.txt"

def upload_to_gcs(local_path: str, gcs_path: str):
    """Realiza o upload de um arquivo local para o GCS."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(local_path)
        return True
    except Exception as e:
        logger.error(f"Erro ao fazer upload para GCS ({local_path} -> {gcs_path}): {e}")
        return False

def log_debug(source: str, query: str, nodes: List[NodeWithScore]):
    """Escreve a saída completa do retrieval em um arquivo de debug."""
    return
    try:
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"DATA/HORA: {datetime.now().isoformat()}\n")
            f.write(f"FONTE: {source}\n")
            f.write(f"QUERY: {query}\n")
            f.write(f"{'-'*80}\n")
            for i, n in enumerate(nodes):
                f.write(f"RESULTADO {i+1} [Score: {n.score:.4f} if hasattr(n, 'score') else 'N/A']\n")
                f.write(f"METADADOS: {n.node.metadata}\n")
                # Usa get_content() para evitar erro de atributo desconhecido em BaseNode
                text_content = n.node.get_content() if hasattr(n.node, 'get_content') else str(n.node)
                f.write(f"CONTEÚDO:\n{text_content[:2000]}...\n") 
                f.write(f"{'.'*40}\n")
            f.write(f"{'='*80}\n")
    except Exception as e:
        logger.error(f"Erro ao escrever log de debug: {e}")

def fetch_markdown_from_gcs(pdf_nome: str) -> Optional[str]:
    """
    Busca o conteúdo integral de um arquivo Markdown no GCS.
    Caminho esperado: parsed_docs/pdfs/{pdf_nome}.md
    """
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        
        # Garante o nome correto: remove .pdf se existir e adiciona .pdf.md conforme padrão
        base_name = pdf_nome.replace(".pdf", "")
        blob_path = f"parsed_docs/pdfs/{base_name}.pdf.md"
            
        blob = bucket.blob(blob_path)
        
        if not blob.exists():
            logger.warning(f"Markdown não encontrado no GCS: {blob_path}")
            return None

        content = blob.download_as_text(encoding="utf-8")
        return content
    except Exception as e:
        logger.error(f"Erro ao buscar Markdown no GCS ({pdf_nome}): {e}")
        return None

def generate_pdf_signed_url(pdf_nome: str, expiration_minutes: int = 60) -> Optional[str]:
    """
    Gera uma URL assinada para acesso temporário ao PDF original.
    Caminho esperado: pdfs/{pdf_nome}
    """
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        
        # Garante que estamos apontando para o PDF original na raiz da pasta pdfs/
        name_with_ext = pdf_nome if pdf_nome.endswith(".pdf") else f"{pdf_nome}.pdf"
        
        blob_path = f"pdfs/{name_with_ext}"
        blob = bucket.blob(blob_path)

        # Gera a URL com validade temporária
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
        return url
    except Exception as e:
        logger.error(f"Erro ao gerar Signed URL para {pdf_nome}: {e}")
        return None

class GCSFullDocumentRetriever(BaseRetriever):
    """
    Retriever customizado para a coleção de PDFs.
    Busca chunks no Qdrant e recupera o documento completo no GCS (Parent Retrieval).
    """
    def __init__(self, vector_retriever: BaseRetriever):
        self._vector_retriever = vector_retriever
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # 1. Busca os chunks mais relevantes (Small chunks)
        logger.info(f"Iniciando busca vetorial no Qdrant (Coleção: {COLLECTION_PDFS}). Query: '{query_bundle.query_str[:50]}...'")
        nodes_with_score = self._vector_retriever.retrieve(query_bundle)
        
        final_nodes: List[NodeWithScore] = []
        processed_files = set() 

        for node_with_score in nodes_with_score:
            pdf_nome = node_with_score.node.metadata.get("pdf_nome")
            
            if not pdf_nome or pdf_nome in processed_files:
                continue

            # 2. Busca o documento completo no GCS (Big context)
            logger.info(f"Realizando Parent Retrieval (GCS): {pdf_nome}")
            full_text = fetch_markdown_from_gcs(pdf_nome)

            if full_text:
                pdf_link = generate_pdf_signed_url(pdf_nome)
                
                header = f"--- ARQUIVO ORIGINAL: {pdf_nome} ---\n"
                if pdf_link:
                    header += f"--- LINK DE ACESSO: {pdf_link} ---\n\n"
                
                new_node = TextNode(
                    text=header + full_text,
                    metadata=node_with_score.node.metadata
                )
                new_node.metadata["retrieval_type"] = "GCS_Full_Document"
                if pdf_link:
                    new_node.metadata["pdf_url_acesso"] = pdf_link
                
                final_nodes.append(NodeWithScore(node=new_node, score=node_with_score.score))
                processed_files.add(pdf_nome)
            else:
                node_with_score.node.metadata["retrieval_type"] = "Chunk_Only_Fallback"
                final_nodes.append(node_with_score)
        
        # LOG DE DEBUG: Qdrant + GCS
        log_debug(f"RETRIEVAL PDFs (QDRANT + GCS)", query_bundle.query_str, final_nodes)
                
        return final_nodes
