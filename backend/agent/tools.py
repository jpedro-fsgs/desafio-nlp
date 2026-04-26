from typing import Optional, List, Any
from llama_index.core.tools import FunctionTool
from llama_index.core.vector_stores.types import MetadataFilters, ExactMatchFilter
from services.qdrant import get_registros_query_engine, get_pdfs_query_engine
from services.gcs import fetch_markdown_from_gcs, log_debug
from models import SourceModel, ToolResponseModel
from config import logger

def get_agent_tools() -> list:
    """Inicializa e retorna a lista de ferramentas modularizadas e resilientes com contrato Pydantic."""
    
    # 1. Ferramenta de busca macro (Registros)
    async def pesquisar_registros(query: str, registro_id: Optional[int] = None, situacao: Optional[str] = None) -> ToolResponseModel:
        """
        Busca ementas e metadados de resoluções e portarias da ANEEL.
        Você pode filtrar por registro_id (ID numérico) ou situacao (ex: 'VIGENTE').
        """
        try:
            filters: Optional[MetadataFilters] = None
            if registro_id or situacao:
                filter_list = []
                if registro_id:
                    filter_list.append(ExactMatchFilter(key="registro_id", value=registro_id))
                if situacao:
                    filter_list.append(ExactMatchFilter(key="situacao", value=situacao))
                filters = MetadataFilters(filters=filter_list)

            engine = get_registros_query_engine(filters=filters)
            response = await engine.aquery(query)
            
            # LOG DE DEBUG: Registros
            if hasattr(response, 'source_nodes'):
                log_debug("RETRIEVAL REGISTROS (QDRANT)", query, response.source_nodes)

            sources_list = []
            meta_str = "\n\nFONTES E METADADOS RECUPERADOS:\n"
            
            if hasattr(response, 'source_nodes') and response.source_nodes:
                for i, n in enumerate(response.source_nodes):
                    m = n.node.metadata
                    rid = str(m.get('registro_id', ''))
                    tit = m.get('titulo', 'Documento')
                    dat = m.get('data_iso', 'S/D')
                    sit = m.get('situacao', 'Desconhecida')
                    # Resolvendo erro de Pylance: usando get_content() em vez de .text
                    ementa = m.get('ementa') or n.node.get_content()
                    
                    # Adiciona ao contrato Pydantic
                    sources_list.append(SourceModel(
                        id=rid or f"reg_{i}",
                        title=tit,
                        tool_name="pesquisar_registros_aneel",
                        text=ementa # Campo de texto para ementa
                    ))
                    
                    meta_str += f"[{i+1}] ID: {rid} | Norma: {tit} | Data: {dat} | Status: {sit}\n"
            else:
                meta_str += "Nenhum metadado detalhado disponível para esta resposta.\n"

            text_result = f"RESULTADO DA BUSCA DE REGISTROS (EMENTAS):\n---\n{str(response)}\n---{meta_str}"
            return ToolResponseModel(text=text_result, sources=sources_list)

        except Exception as e:
            logger.error(f"[TOOL ERROR] pesquisar_registros: {e}")
            return ToolResponseModel(text=f"ERRO NA BUSCA DE REGISTROS: {str(e)}", sources=[])

    registros_tool = FunctionTool.from_defaults(
        async_fn=pesquisar_registros,
        name="pesquisar_registros_aneel",
        description="Busca informações gerais e ementas. Use parâmetros opcionais para filtrar por ID ou situação."
    )

    # 2. Ferramenta de busca técnica profunda (PDFs)
    async def pesquisar_documentos_tecnicos(query: str, registro_id: Optional[int] = None, natureza: Optional[str] = None) -> ToolResponseModel:
        """
        Busca detalhes técnicos dentro do conteúdo integral dos PDFs.
        Você pode filtrar por registro_id para ver anexos de uma norma específica.
        """
        try:
            filters: Optional[MetadataFilters] = None
            if registro_id or natureza:
                filter_list = []
                if registro_id:
                    filter_list.append(ExactMatchFilter(key="registro_id", value=registro_id))
                if natureza:
                    filter_list.append(ExactMatchFilter(key="natureza", value=natureza))
                filters = MetadataFilters(filters=filter_list)

            engine = get_pdfs_query_engine(filters=filters)
            response = await engine.aquery(query)
            
            sources_list = []
            meta_str = "\n\nFONTES, ARQUIVOS E LINKS RECUPERADOS:\n"
            
            if hasattr(response, 'source_nodes') and response.source_nodes:
                for i, n in enumerate(response.source_nodes):
                    m = n.node.metadata
                    rid = str(m.get('registro_id', ''))
                    arq = m.get('pdf_nome', 'Desconhecido')
                    nat = m.get('natureza', 'Técnico')
                    link = m.get('pdf_url_acesso') # Chave correta no Qdrant: url_origem
                    
                    # Adiciona ao contrato Pydantic
                    sources_list.append(SourceModel(
                        id=arq,
                        title=arq,
                        link=link,
                        tool_name="pesquisar_documentos_pdf_aneel",
                        # Para PDFs, mantemos apenas o link clicável no frontend, 
                        # removendo o campo 'text' que geraria o collapsible indesejado.
                        text=None 
                    ))
                    
                    meta_str += f"[{i+1}] Registro ID: {rid} | Arquivo: {arq} | Tipo: {nat}\n"
                    meta_str += f"    -> LINK DE ACESSO: {link or 'Não disponível'}\n"
            else:
                meta_str += "Nenhum documento técnico específico detalhado.\n"

            text_result = f"RESULTADO DA BUSCA TÉCNICA (CONTEÚDO DOS DOCUMENTOS):\n---\n{str(response)}\n---{meta_str}"
            return ToolResponseModel(text=text_result, sources=sources_list)

        except Exception as e:
            logger.error(f"[TOOL ERROR] pesquisar_documentos_tecnicos: {e}")
            return ToolResponseModel(text=f"ERRO NA BUSCA TÉCNICA: {str(e)}", sources=[])

    pdfs_tool = FunctionTool.from_defaults(
        async_fn=pesquisar_documentos_tecnicos,
        name="pesquisar_documentos_pdf_aneel",
        description="Busca detalhes técnicos complexos. Filtre por registro_id para focar em uma norma conhecida."
    )

    # 3. Ferramenta de leitura direta
    async def ler_documento_completo(pdf_nome: str) -> ToolResponseModel:
        """Lê o conteúdo integral de um arquivo Markdown diretamente do GCS."""
        try:
            from services.gcs import generate_pdf_signed_url
            logger.info(f"[TOOL] Leitura direta: {pdf_nome}")
            
            content = fetch_markdown_from_gcs(pdf_nome)
            pdf_link = generate_pdf_signed_url(pdf_nome)
            
            if content:
                link_str = f"\n\nLINK PARA DOWNLOAD DO PDF ORIGINAL: {pdf_link}" if pdf_link else ""
                text_result = f"Conteúdo integral do arquivo {pdf_nome}:\n\n{content}{link_str}"
                
                source = SourceModel(
                    id=pdf_nome,
                    title=pdf_nome,
                    link=pdf_link,
                    tool_name="ler_documento_completo_direto",
                    # Nesta ferramenta específica de leitura, o texto é o objetivo, 
                    # mas para manter a consistência visual de 'PDF = Link', 
                    # podemos optar por não mostrar o collapsible gigante no painel lateral.
                    text=None 
                )
                
                return ToolResponseModel(text=text_result, sources=[source])
            
            return ToolResponseModel(text=f"Erro: Arquivo {pdf_nome} não encontrado no storage.", sources=[])
        except Exception as e:
            logger.error(f"[TOOL ERROR] ler_documento_completo: {e}")
            return ToolResponseModel(text=f"Erro técnico ao ler {pdf_nome}: {str(e)}", sources=[])

    direct_read_tool = FunctionTool.from_defaults(
        async_fn=ler_documento_completo,
        name="ler_documento_completo_direto",
        description="Lê o texto integral de um arquivo específico quando você já sabe o nome dele."
    )

    return [registros_tool, pdfs_tool, direct_read_tool]
