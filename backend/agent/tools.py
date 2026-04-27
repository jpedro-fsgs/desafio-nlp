from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from llama_index.core.tools import FunctionTool
from llama_index.core.vector_stores.types import MetadataFilters, ExactMatchFilter, MetadataFilter, FilterOperator
from services.qdrant import get_registros_query_engine, get_pdfs_query_engine
from services.gcs import fetch_markdown_from_gcs, log_debug
from models import SourceModel, ToolResponseModel
from config import logger

# --- SCHEMAS DE CONTRATO FORTE (Pydantic) ---

class PesquisarRegistrosSchema(BaseModel):
    query: str = Field(
        ..., 
        description="Termos de busca semântica para encontrar normas. Use palavras-chave sobre o assunto (ex: 'tarifas de transmissão', 'geração distribuída')."
    )
    registro_id: Optional[int] = Field(
        None, 
        description="ID numérico único da norma. Use quando o usuário citar um ID específico ou para validar metadados de uma norma já conhecida."
    )
    situacao: Optional[str] = Field(
        None, 
        description=(
            "Estado de validade da norma. VALORES ACEITOS: "
            "'NÃO CONSTA REVOGAÇÃO EXPRESSA' (Vigente/Ativa), "
            "'REVOGADA' (Não vale mais), 'SUSPENSA', 'TORNADA SEM EFEITO'. "
            "DICA: Sempre verifique este campo para não citar normas inválidas como se fossem atuais."
        )
    )
    data_inicio: Optional[str] = Field(
        None, 
        description="Data inicial do período de publicação (formato ISO: YYYY-MM-DD). Use para buscas como 'normas de 2021 em diante'."
    )
    data_fom: Optional[str] = Field(
        None, 
        alias="data_fim",
        description="Data final do período de publicação (formato ISO: YYYY-MM-DD). Use para limitar buscas até um ponto no tempo."
    )
    data_iso: Optional[str] = Field(
        None, 
        description="Data exata de publicação (YYYY-MM-DD). Use quando o usuário perguntar por um dia específico."
    )

class PesquisarDocumentosSchema(BaseModel):
    query: str = Field(
        ..., 
        description="Termos técnicos para buscar dentro do texto INTEGRAL dos PDFs. Ideal para encontrar cálculos, tabelas, fórmulas e justificativas detalhadas."
    )
    registro_id: Optional[int] = Field(
        None, 
        description="ID da norma 'pai'. Use para buscar informações apenas nos anexos, votos e notas técnicas vinculados a uma resolução específica."
    )
    pdf_nome: Optional[str] = Field(
        None, 
        description="Nome exato do arquivo (ex: 'ren20211000.pdf'). Use para pesquisar trechos dentro de um arquivo que você já identificou anteriormente."
    )
    natureza: Optional[str] = Field(
        None, 
        description=(
            "Categoria técnica do arquivo. EXEMPLOS: 'Voto', 'Nota Técnica', 'Resolução Autorizativa', "
            "'Anexo de Resolução Autorizativa', 'Extrato de Contrato', 'Despacho'. "
            "DICA: Se o usuário quer a 'justificativa' da diretoria, filtre por natureza='Voto'."
        )
    )
    sigla: Optional[str] = Field(
        None, 
        description="Sigla abreviada do tipo de norma. EXEMPLOS: 'DSP' (Despacho), 'REA' (Resolução Autorizativa), 'PRT' (Portaria), 'REH' (Resolução Homologatória), 'REN' (Resolução Normativa)."
    )

class LerDocumentoSchema(BaseModel):
    pdf_nome: str = Field(
        ..., 
        description=(
            "Nome exato do arquivo PDF (ex: 'rea202212715ti.pdf'). "
            "ESTA É A FERRAMENTA MAIS PODEROSA: Use-a para ler o texto COMPLETO (Markdown) "
            "quando precisar de precisão absoluta, verificar trechos rasurados (revogados) "
            "ou entender a estrutura inteira de um documento."
        )
    )

def get_agent_tools() -> list:
    """Inicializa as ferramentas com descrições extensivas para guiar o raciocínio do agente."""
    
    # 1. Ferramenta de busca macro (Registros)
    async def pesquisar_registros(
        query: str, 
        registro_id: Optional[int] = None, 
        situacao: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        data_iso: Optional[str] = None
    ) -> ToolResponseModel:
        """
        ESTRATÉGIA: Esta é a porta de entrada. Use para localizar quais normas existem sobre um tema, 
        descobrir seus IDs e verificar se ainda estão vigentes (situação). 
        Retorna ementas e metadados básicos.
        """
        try:
            filter_list = []
            if registro_id:
                filter_list.append(ExactMatchFilter(key="registro_id", value=registro_id))
            if situacao:
                filter_list.append(ExactMatchFilter(key="situacao", value=situacao))
            if data_iso:
                filter_list.append(ExactMatchFilter(key="data_iso", value=data_iso))
            if data_inicio:
                filter_list.append(MetadataFilter(key="data_iso", value=data_inicio, operator=FilterOperator.GTE))
            if data_fim:
                filter_list.append(MetadataFilter(key="data_iso", value=data_fim, operator=FilterOperator.LTE))

            filters = MetadataFilters(filters=filter_list) if filter_list else None
            engine = get_registros_query_engine(filters=filters)
            response = await engine.aquery(query)
            
            if hasattr(response, 'source_nodes'):
                log_debug("RETRIEVAL REGISTROS", query, response.source_nodes)

            sources_list = []
            meta_str = "\n\nFONTES ENCONTRADAS (EMENTAS):\n"
            
            if hasattr(response, 'source_nodes') and response.source_nodes:
                for i, n in enumerate(response.source_nodes):
                    m = n.node.metadata
                    rid = str(m.get('registro_id', ''))
                    tit = m.get('titulo', 'Documento')
                    sit = m.get('situacao', 'Desconhecida')
                    dat = m.get('data_iso', 'S/D')
                    ementa = m.get('ementa') or n.node.get_content()
                    
                    sources_list.append(SourceModel(
                        id=rid or f"reg_{i}",
                        title=tit,
                        tool_name="pesquisar_registros_aneel",
                        text=ementa
                    ))
                    meta_str += f"[{i+1}] ID: {rid} | Norma: {tit} | Data: {dat} | Status: {sit}\n"
            
            text_result = f"RESULTADO DA BUSCA DE REGISTROS (Resumo das Normas):\n---\n{str(response)}\n---{meta_str}"
            return ToolResponseModel(text=text_result, sources=sources_list)
        except Exception as e:
            logger.error(f"Erro em pesquisar_registros: {e}")
            return ToolResponseModel(text=f"Erro técnico na busca de registros: {e}", sources=[])

    # 2. Ferramenta de busca técnica profunda (PDFs)
    async def pesquisar_documentos_tecnicos(
        query: str, 
        registro_id: Optional[int] = None, 
        pdf_nome: Optional[str] = None,
        natureza: Optional[str] = None,
        sigla: Optional[str] = None
    ) -> ToolResponseModel:
        """
        ESTRATÉGIA: Use quando precisar de detalhes técnicos profundos contidos em ANEXOS, VOTOS ou NOTAS TÉCNICAS. 
        Diferente da busca de registros, esta pesquisa dentro do conteúdo textual dos arquivos. 
        Se você já tem o registro_id de uma norma, use-o aqui para encontrar os anexos específicos dela.
        """
        try:
            filter_list = []
            if registro_id:
                filter_list.append(ExactMatchFilter(key="registro_id", value=registro_id))
            if pdf_nome:
                filter_list.append(ExactMatchFilter(key="pdf_nome", value=pdf_nome))
            if natureza:
                filter_list.append(ExactMatchFilter(key="natureza", value=natureza))
            if sigla:
                filter_list.append(ExactMatchFilter(key="sigla", value=sigla))
                
            filters = MetadataFilters(filters=filter_list) if filter_list else None
            engine = get_pdfs_query_engine(filters=filters)
            response = await engine.aquery(query)
            
            sources_list = []
            meta_str = "\n\nARQUIVOS TÉCNICOS LOCALIZADOS:\n"
            
            if hasattr(response, 'source_nodes') and response.source_nodes:
                for i, n in enumerate(response.source_nodes):
                    m = n.node.metadata
                    arq = m.get('pdf_nome', 'Desconhecido')
                    nat = m.get('natureza', 'Técnico')
                    link = m.get('url_origem')
                    
                    sources_list.append(SourceModel(
                        id=arq,
                        title=arq,
                        link=link,
                        tool_name="pesquisar_documentos_pdf_aneel",
                        text=None 
                    ))
                    meta_str += f"[{i+1}] Arquivo: {arq} | Tipo: {nat} | Link: {link}\n"
            
            text_result = f"RESULTADO DA BUSCA TÉCNICA (Detalhes em PDFs):\n---\n{str(response)}\n---{meta_str}"
            return ToolResponseModel(text=text_result, sources=sources_list)
        except Exception as e:
            logger.error(f"Erro em pesquisar_documentos_tecnicos: {e}")
            return ToolResponseModel(text=f"Erro técnico na busca profunda: {e}", sources=[])

    # 3. Ferramenta de leitura direta
    async def ler_documento_completo(pdf_nome: str) -> ToolResponseModel:
        """
        ESTRATÉGIA: Use esta ferramenta para obter o texto INTEGRAL de um documento específico. 
        É essencial para: 1. Analisar revogações (trechos rasurados ~~assim~~); 2. Ler artigos completos; 
        3. Entender o contexto total de uma norma que você já identificou pelo nome.
        """
        try:
            from services.gcs import generate_pdf_signed_url
            content = fetch_markdown_from_gcs(pdf_nome)
            pdf_link = generate_pdf_signed_url(pdf_nome)
            
            if content:
                source = SourceModel(
                    id=pdf_nome,
                    title=pdf_nome,
                    link=pdf_link,
                    tool_name="ler_documento_completo_direto",
                    text=None 
                )
                return ToolResponseModel(text=content, sources=[source])
            return ToolResponseModel(text=f"Aviso: O arquivo {pdf_nome} não pôde ser encontrado no armazenamento integral.", sources=[])
        except Exception as e:
            logger.error(f"Erro em ler_documento_completo: {e}")
            return ToolResponseModel(text=f"Erro técnico ao tentar ler o arquivo completo: {e}", sources=[])

    # Registro das ferramentas com schemas e descrições estratégicas
    return [
        FunctionTool.from_defaults(
            async_fn=pesquisar_registros,
            name="pesquisar_registros_aneel",
            description="Localiza normas, descobre IDs e verifica validade/situação jurídica. Ponto de partida obrigatório.",
            fn_schema=PesquisarRegistrosSchema
        ),
        FunctionTool.from_defaults(
            async_fn=pesquisar_documentos_tecnicos,
            name="pesquisar_documentos_pdf_aneel",
            description="Busca profunda em anexos, votos e justificativas técnicas. Use quando ementas não bastarem.",
            fn_schema=PesquisarDocumentosSchema
        ),
        FunctionTool.from_defaults(
            async_fn=ler_documento_completo,
            name="ler_documento_completo_direto",
            description="Lê o texto integral de um documento conhecido. Use para precisão absoluta e análise de revogações.",
            fn_schema=LerDocumentoSchema
        )
    ]
