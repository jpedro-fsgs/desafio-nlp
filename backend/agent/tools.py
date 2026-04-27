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
        description="Consulta em linguagem natural sobre o tema regulatório (ex: 'tarifas de transmissão', 'geração distribuída'). Use para busca semântica em ementas de normas."
    )
    registro_id: Optional[int] = Field(
        None, 
        description="O identificador numérico único de uma norma. Utilize este campo se o usuário mencionar um ID específico para busca direta ou validação."
    )
    situacao: Optional[str] = Field(
        None, 
        description=(
            "Filtro pelo estado de validade da norma. VALORES OBRIGATÓRIOS: "
            "'NÃO CONSTA REVOGAÇÃO EXPRESSA' (para normas vigentes), "
            "'REVOGADA', 'SUSPENSA', 'TORNADA SEM EFEITO'. "
            "IMPORTANTE: Sempre valide se uma norma ainda é vigente antes de apresentá-la como regra atual."
        )
    )
    data_inicio: Optional[str] = Field(
        None, 
        description="Data inicial do período de publicação no formato ISO (YYYY-MM-DD). Exemplo: '2021-01-01'."
    )
    data_fim: Optional[str] = Field(
        None, 
        description="Data final do período de publicação no formato ISO (YYYY-MM-DD). Exemplo: '2023-12-31'."
    )
    data_iso: Optional[str] = Field(
        None, 
        description="Data exata da publicação da norma (YYYY-MM-DD). Use para buscar normas publicadas em um dia específico."
    )

class PesquisarDocumentosSchema(BaseModel):
    query: str = Field(
        ..., 
        description="Termos técnicos ou perguntas específicas para buscar no CONTEÚDO INTEGRAL dos documentos (PDFs). Ideal para encontrar cálculos, tabelas, fórmulas e justificativas."
    )
    registro_id: Optional[int] = Field(
        None, 
        description="ID da norma vinculada. Use para restringir a busca apenas aos documentos (votos, notas técnicas, anexos) de uma resolução específica."
    )
    pdf_nome: Optional[str] = Field(
        None, 
        description="Nome exato do arquivo PDF (ex: 'ren20211000.pdf'). Utilize se você já souber qual arquivo deseja explorar."
    )
    natureza: Optional[str] = Field(
        None, 
        description=(
            "Tipo técnico do documento. Exemplos comuns: 'Voto' (contém a justificativa da decisão), "
            "'Nota Técnica', 'Resolução Autorizativa', 'Anexo', 'Despacho'. "
            "DICA: Para entender POR QUE uma decisão foi tomada, procure por natureza='Voto'."
        )
    )
    sigla: Optional[str] = Field(
        None, 
        description="Sigla do tipo de norma (ex: REN, REA, REH, DSP). Útil para filtrar tipos específicos de atos regulatórios."
    )

class LerDocumentoSchema(BaseModel):
    pdf_nome: str = Field(
        ..., 
        description=(
            "O nome exato do arquivo PDF para leitura integral (ex: 'rea202212715ti.pdf'). "
            "FERRAMENTA CRÍTICA: Use para ler o texto completo em Markdown, essencial para análise de "
            "detalhes, artigos específicos e identificação de trechos revogados (marcados com ~~rasurado~~)."
        )
    )

def get_agent_tools() -> list:
    """Inicializa as ferramentas com descrições otimizadas para o Gemini."""
    
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
        ESTRATEGIA DE BUSCA DE REGISTROS:
        Utilize esta ferramenta como PONTO DE PARTIDA para localizar quais normas existem sobre um tema. 
        Ela retorna metadados (ementa, título, situação, data) que permitem identificar o registro_id 
        necessário para buscas mais profundas. SEMPRE verifique a 'situação' para garantir a validade jurídica.
        """
        logger.info(f"[TOOL:pesquisar_registros] Query: '{query}' | ID: {registro_id} | Situação: {situacao}")
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

            if filter_list:
                logger.debug(f"[TOOL:pesquisar_registros] Filtros aplicados: {[f.key for f in filter_list]}")

            filters = MetadataFilters(filters=filter_list) if filter_list else None
            engine = get_registros_query_engine(filters=filters)
            
            logger.debug(f"[TOOL:pesquisar_registros] Executando query no engine...")
            response = await engine.aquery(query)
            
            if hasattr(response, 'source_nodes'):
                log_debug("RETRIEVAL REGISTROS", query, response.source_nodes)
                logger.info(f"[TOOL:pesquisar_registros] Encontrados {len(response.source_nodes)} nós de origem.")

            sources_list = []
            meta_str = "\n\nFONTES ENCONTRADAS (METADADOS DAS NORMAS):\n"
            
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
            logger.error(f"[TOOL:pesquisar_registros] Erro crítico: {e}", exc_info=True)
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
        ESTRATEGIA DE BUSCA TÉCNICA:
        Utilize esta ferramenta para pesquisar DENTRO do texto de documentos vinculados (Anexos, Votos, Notas Técnicas). 
        É ideal para responder perguntas sobre 'como' algo é calculado ou 'por que' uma decisão foi tomada. 
        Se você já possui um registro_id, use-o aqui para filtrar apenas os documentos daquela norma.
        Sempre que possível complemente a busca de ementas com esta ferramenta para obter a JUSTIFICATIVA COMPLETA por trás de uma decisão regulatória.
        """
        logger.info(f"[TOOL:pesquisar_documentos] Query: '{query}' | RegID: {registro_id} | PDF: {pdf_nome} | Natureza: {natureza}")
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
                
            if filter_list:
                logger.debug(f"[TOOL:pesquisar_documentos] Filtros aplicados: {[f.key for f in filter_list]}")

            filters = MetadataFilters(filters=filter_list) if filter_list else None
            engine = get_pdfs_query_engine(filters=filters)
            
            logger.debug(f"[TOOL:pesquisar_documentos] Executando query técnica no engine...")
            response = await engine.aquery(query)
            
            if hasattr(response, 'source_nodes'):
                logger.info(f"[TOOL:pesquisar_documentos] Encontrados {len(response.source_nodes)} trechos técnicos.")

            sources_list = []
            meta_str = "\n\nDOCUMENTOS TÉCNICOS LOCALIZADOS:\n"
            
            if hasattr(response, 'source_nodes') and response.source_nodes:
                for i, n in enumerate(response.source_nodes):
                    m = n.node.metadata
                    arq = m.get('pdf_nome', 'Desconhecido')
                    nat = m.get('natureza', 'Técnico')
                    link = m.get('pdf_url_acesso') or m.get('url_origem') or "Link Indisponível"
                    
                    sources_list.append(SourceModel(
                        id=arq,
                        title=arq,
                        link=link,
                        tool_name="pesquisar_documentos_pdf_aneel",
                        text=None 
                    ))
                    meta_str += f"[{i+1}] Arquivo: {arq} | Tipo: {nat} | Link: {link}\n"
            
            text_result = f"RESULTADO DA BUSCA TÉCNICA (Trechos de Documentos):\n---\n{str(response)}\n---{meta_str}"
            return ToolResponseModel(text=text_result, sources=sources_list)
        except Exception as e:
            logger.error(f"[TOOL:pesquisar_documentos] Erro técnico profundo: {e}", exc_info=True)
            return ToolResponseModel(text=f"Erro técnico na busca profunda: {e}", sources=[])

    # 3. Ferramenta de leitura direta
    async def ler_documento_completo(pdf_nome: str) -> ToolResponseModel:
        """
        ESTRATEGIA DE LEITURA INTEGRAL:
        Esta ferramenta deve ser usada quando você precisa da PRECISÃO TOTAL do texto ou quer analisar a 
        estrutura completa de um documento já identificado. Essencial para verificar trechos revogados (riscados) 
        que podem não ser capturados corretamente em buscas de fragmentos.
        """
        logger.info(f"[TOOL:ler_documento] Solicitado: {pdf_nome}")
        try:
            from services.gcs import generate_pdf_signed_url
            
            logger.debug(f"[TOOL:ler_documento] Buscando Markdown do GCS...")
            content = fetch_markdown_from_gcs(pdf_nome)
            
            logger.debug(f"[TOOL:ler_documento] Gerando URL assinada para o PDF...")
            pdf_link = generate_pdf_signed_url(pdf_nome)
            
            if content:
                logger.info(f"[TOOL:ler_documento] Sucesso ao carregar {pdf_nome} ({len(content)} caracteres).")
                source = SourceModel(
                    id=pdf_nome,
                    title=pdf_nome,
                    link=pdf_link,
                    tool_name="ler_documento_completo_direto",
                    text=None 
                )
                return ToolResponseModel(text=content, sources=[source])
            
            logger.warning(f"[TOOL:ler_documento] Arquivo {pdf_nome} não localizado.")
            return ToolResponseModel(text=f"Aviso: O arquivo {pdf_nome} não foi encontrado para leitura integral.", sources=[])
        except Exception as e:
            logger.error(f"[TOOL:ler_documento] Erro ao ler documento integral: {e}", exc_info=True)
            return ToolResponseModel(text=f"Erro técnico ao acessar o conteúdo integral: {e}", sources=[])

    # Registro das ferramentas com schemas e descrições estratégicas
    return [
        FunctionTool.from_defaults(
            async_fn=pesquisar_registros,
            name="pesquisar_registros_aneel",
            description="Busca por normas (Resoluções, Portarias, Despachos) e metadados. Use para iniciar qualquer pesquisa.",
            fn_schema=PesquisarRegistrosSchema
        ),
        FunctionTool.from_defaults(
            async_fn=pesquisar_documentos_tecnicos,
            name="pesquisar_documentos_pdf_aneel",
            description="Pesquisa profunda no texto de anexos, votos e notas técnicas. Use para detalhes técnicos e justificativas.",
            fn_schema=PesquisarDocumentosSchema
        ),
        FunctionTool.from_defaults(
            async_fn=ler_documento_completo,
            name="ler_documento_completo_direto",
            description="Lê o conteúdo Markdown integral de um arquivo PDF específico. Essencial para precisão absoluta.",
            fn_schema=LerDocumentoSchema
        )
    ]
