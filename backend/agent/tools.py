from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from services.qdrant import get_registros_query_engine, get_pdfs_query_engine
from services.gcs import fetch_markdown_from_gcs
from config import logger

def get_agent_tools() -> list:
    """Inicializa e retorna a lista de ferramentas modularizadas e resilientes."""
    
    # 1. Ferramenta de busca macro (Registros)
    async def pesquisar_registros(query: str) -> str:
        """Busca ementas e metadados de resoluções e portarias."""
        try:
            engine = get_registros_query_engine()
            response = await engine.aquery(query)
            return f"RESULTADO DA BUSCA DE REGISTROS (EMENTAS):\n---\n{str(response)}\n---"
        except Exception as e:
            logger.error(f"[TOOL ERROR] pesquisar_registros: {e}")
            return f"ERRO NA BUSCA DE REGISTROS: {str(e)}. Tente usar a busca técnica de PDFs."

    registros_tool = FunctionTool.from_defaults(
        async_fn=pesquisar_registros,
        name="pesquisar_registros_aneel",
        description="Busca informações gerais, ementas e situações de resoluções e portarias da ANEEL."
    )

    # 2. Ferramenta de busca técnica profunda (PDFs)
    async def pesquisar_documentos_tecnicos(query: str) -> str:
        """Busca detalhes técnicos dentro do conteúdo integral dos PDFs."""
        try:
            engine = get_pdfs_query_engine()
            response = await engine.aquery(query)
            return f"RESULTADO DA BUSCA TÉCNICA (CONTEÚDO DOS DOCUMENTOS):\n---\n{str(response)}\n---"
        except Exception as e:
            logger.error(f"[TOOL ERROR] pesquisar_documentos_tecnicos: {e}")
            return f"ERRO NA BUSCA TÉCNICA: {str(e)}. Verifique se a base de PDFs está disponível."

    pdfs_tool = FunctionTool.from_defaults(
        async_fn=pesquisar_documentos_tecnicos,
        name="pesquisar_documentos_pdf_aneel",
        description="Busca detalhes técnicos complexos e tabelas no texto integral de anexos e notas técnicas."
    )

    # 3. Ferramenta de leitura direta
    async def ler_documento_completo(pdf_nome: str) -> str:
        """Lê o conteúdo integral de um arquivo Markdown diretamente do GCS."""
        try:
            from services.gcs import generate_pdf_signed_url
            logger.info(f"[TOOL] Leitura direta: {pdf_nome}")
            
            content = fetch_markdown_from_gcs(pdf_nome)
            pdf_link = generate_pdf_signed_url(pdf_nome)
            
            if content:
                link_str = f"\n\nLINK PARA DOWNLOAD DO PDF ORIGINAL: {pdf_link}" if pdf_link else ""
                return f"Conteúdo integral do arquivo {pdf_nome}:\n\n{content}{link_str}"
            
            return f"Erro: Arquivo {pdf_nome} não encontrado no storage. Verifique se o nome está correto."
        except Exception as e:
            logger.error(f"[TOOL ERROR] ler_documento_completo: {e}")
            return f"Erro técnico ao tentar ler o arquivo {pdf_nome}: {str(e)}"

    direct_read_tool = FunctionTool.from_defaults(
        async_fn=ler_documento_completo,
        name="ler_documento_completo_direto",
        description="Lê o texto integral de um arquivo específico quando você já sabe o nome dele."
    )

    return [registros_tool, pdfs_tool, direct_read_tool]
