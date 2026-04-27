import json
from datetime import datetime, timedelta
from typing import Dict, AsyncGenerator
from llama_index.core.agent.workflow import FunctionAgent, ToolCall, AgentStream, ToolCallResult
from llama_index.core.workflow import Context
from agent.tools import get_agent_tools
from models import ToolResponseModel, SourceModel
from config import Settings, logger

# --- GERENCIAMENTO DE CONTEXTO E HISTÓRICO (SESSÕES V0.14) ---
# session_id -> Context (Memória interna do LlamaIndex)
_session_contexts: Dict[str, Context] = {}
# session_id -> Histórico Visual (Para reconstrução da UI no Streamlit)
_chat_histories: Dict[str, dict] = {}
# session_id -> Última atividade
_last_activity: Dict[str, datetime] = {}

def _cleanup_inactive_sessions():
    """Remove sessões que não tiveram atividade na última hora."""
    now = datetime.now()
    cutoff = now - timedelta(hours=1)

    inactive_sessions = [
        sid for sid, last_time in _last_activity.items() 
        if last_time < cutoff
    ]

    for sid in inactive_sessions:
        logger.info(f"[CLEANUP] Removendo sessão inativa: {sid}")
        _session_contexts.pop(sid, None)
        _chat_histories.pop(sid, None)
        _last_activity.pop(sid, None)

def _update_activity(session_id: str):
    """Atualiza o timestamp de última atividade da sessão."""
    _last_activity[session_id] = datetime.now()

def _get_context(session_id: str, agent: FunctionAgent) -> Context:
    """Recupera ou cria um novo contexto de workflow para a sessão."""
    _update_activity(session_id)
    if session_id not in _session_contexts:
        _session_contexts[session_id] = Context(agent)
    return _session_contexts[session_id]

def _init_history(session_id: str, user_id: str):
    """Garante que a estrutura de histórico visual exista para a sessão."""
    _update_activity(session_id)
    if session_id not in _chat_histories:
        _chat_histories[session_id] = {
            "user_id": user_id,
            "title": "Nova Consulta",
            "messages": [],
            "sources": []
        }

# --- SERVIÇO DO AGENTE ---
async def astream_agent_chat(session_id: str, message: str, user_id: str) -> AsyncGenerator[str, None]:
    """Orquestra o chat streaming e persiste o histórico visual em memória."""
    
    _cleanup_inactive_sessions()
    logger.info(f"[CHAT] Sessão {session_id} | Usuário {user_id} | Msg: '{message[:50]}...'")
    
    # Inicializa ou recupera histórico visual
    _init_history(session_id, user_id)
    _chat_histories[session_id]["messages"].append({"role": "user", "content": message})

    # 1. Recupera as Ferramentas do Agente
    tools = get_agent_tools()
    if not tools:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Erro ao inicializar ferramentas do agente.'})}\n\n"
        return

    # 2. Inicializar o Agente de Workflow

    # service.py — system_prompt ajustado
    system_prompt=(
        "Você é um assistente especializado em regulação do setor elétrico brasileiro, "
        "com acesso à base normativa oficial da ANEEL.\n\n"
        "A Base de Dados é composta por normas, documentos e registros de 2016, 2021 e 2022 na maior parte."

        "## FERRAMENTAS DISPONÍVEIS\n"
        "Você possui três ferramentas de pesquisa. Use-as conforme a necessidade da consulta, "
        "sem ordem obrigatória — o contexto da pergunta deve guiar sua estratégia:\n"
        "- 'pesquisar_registros_aneel': para localizar normas por tema e obter metadados (registro_id, título, situação, data).\n"
        "- 'pesquisar_documentos_pdf_aneel': para buscar dentro do conteúdo de Votos, Notas Técnicas e Anexos.\n"
        "- 'ler_documento_completo_direto': para leitura integral de um documento já identificado. "
        "Operação custosa — use quando precisar de precisão absoluta ou análise estrutural completa.\n\n"

        "## NORMAS REVOGADAS — LEITURA OBRIGATÓRIA\n"
        "Normas revogadas são quase integralmente marcadas com ~~strikethrough~~.\n"
        "Normas com situação REVOGADA, SUSPENSA ou TORNADA SEM EFEITO não devem ser descartadas automaticamente. "
        "Seus metadados frequentemente indicam qual norma as revogou, o que pode ser a informação mais relevante "
        "para a consulta. Ao encontrar uma norma revogada:\n"
        "  1. Informe claramente que ela não está mais em vigor.\n"
        "  2. Identifique e busque a norma revogadora nos metadados.\n"
        "  3. Responda com base na norma vigente, contextualizando a evolução normativa quando relevante.\n\n"

        "## TRECHOS REVOGADOS DENTRO DE DOCUMENTOS\n"
        "Ao ler documentos com 'ler_documento_completo_direto', trechos marcados com ~~strikethrough~~ "
        "indicam texto que foi revogado ou torndo sem efeito dentro daquele documento. "
        "Preste atenção rigorosa a essas marcações:\n"
        "  - Nunca cite um trecho ~~riscado~~ como regra vigente.\n"
        "  - Sinalize explicitamente ao usuário que aquele trecho foi revogado.\n"
        "  - Quando possível, identifique o ato que provocou a revogação parcial e busque o texto substituto.\n\n"

        "## REGRAS DE RESPOSTA\n"
        "- Cite sempre: tipo da norma, número e ano (ex: REN nº 1.000/2023).\n"
        "- Se nenhum resultado relevante for encontrado, informe claramente em vez de especular.\n"
        "- Responda somente dentro do escopo da regulação do setor elétrico brasileiro e da base normativa da ANEEL.\n"
        "- Baseie a resposta exclusivamente no contexto recuperado pelas ferramentas.\n"
        "- Não estenda a resposta além do necessário.\n"
        "- Estruture respostas complexas com seções (ex: Fundamento Legal, Detalhamento Técnico, Conclusão).\n"
        "- Nunca afirme algo como vigente sem verificar o campo 'situação' e os trechos do documento.\n"
    )
    agent = FunctionAgent(
        tools=tools,
        llm=Settings.llm,
        system_prompt=system_prompt
    )

    # 3. Recupera o contexto da sessão (contém o histórico)
    ctx = _get_context(session_id, agent)

    # 4. Executa o Workflow com streaming de eventos e limite de segurança adequado
    handler = agent.run(ctx=ctx, user_msg=message, max_steps=20)

    full_assistant_response = ""

    try:
        # Feedback inicial imediato
        yield f"data: {json.dumps({'type': 'status', 'content': 'Pensando'})}\n\n"

        async for ev in handler.stream_events():
            # Evento de Chamada de Ferramenta
            if isinstance(ev, ToolCall):
                # Mapeamento de nomes técnicos para mensagens amigáveis
                tool_map = {
                    "pesquisar_registros_aneel": "Pesquisando registros",
                    "pesquisar_documentos_pdf_aneel": "Pesquisando Documentos",
                    "ler_documento_completo_direto": "Recuperando Documentos"
                }
                msg = tool_map.get(ev.tool_name, f"Analisando: {ev.tool_name}")
                yield f"data: {json.dumps({'type': 'status', 'content': msg})}\n\n"
            
            # Evento de Resultado da Ferramenta (Extração de fontes em tempo real)
            elif isinstance(ev, ToolCallResult):
                sources_payload = []
                output = ev.tool_output
                raw = getattr(output, 'raw_output', None)
                
                # Caso 1: Novo Contrato (ToolResponseModel)
                if isinstance(raw, ToolResponseModel):
                    for src in raw.sources:
                        sources_payload.append(src.model_dump())
                
                # Caso 2: Fallback para QueryEngine direto (se houver tool legada)
                elif raw is not None and hasattr(raw, 'source_nodes'):
                    for node_with_score in raw.source_nodes:
                        m = node_with_score.node.metadata
                        sources_payload.append({
                            "id": str(m.get('registro_id') or m.get('pdf_nome') or "src"),
                            "title": m.get('pdf_nome') or m.get('titulo') or "Documento",
                            "link": m.get('url_origem'),
                            "tool_name": ev.tool_name
                        })
                
                if sources_payload:
                    # Persiste fontes no histórico visual (Deduplicando pelo ID)
                    for sp in sources_payload:
                        if not any(s['id'] == sp['id'] for s in _chat_histories[session_id]["sources"]):
                            _chat_histories[session_id]["sources"].append(sp)
                    
                    yield f"data: {json.dumps({'type': 'sources', 'content': sources_payload})}\n\n"
                
                yield f"data: {json.dumps({'type': 'status', 'content': 'Analisando resultados da pesquisa...'})}\n\n"
            
            # Evento de Token de Resposta
            elif isinstance(ev, AgentStream):
                if ev.delta:
                    full_assistant_response += ev.delta
                    yield f"data: {json.dumps({'type': 'token', 'content': ev.delta})}\n\n"
                else:
                    # Envia um feedback de pensamento quando o token for vazio
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Agente está pensando...'})}\n\n"
        
        # Aguarda a conclusão total do workflow e salva resposta final no histórico visual
        await handler
        _chat_histories[session_id]["messages"].append({"role": "assistant", "content": full_assistant_response})
        
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        logger.info(f"[CHAT] Workflow concluído para sessão {session_id}.")

    except Exception as e:
        logger.error(f"Erro no Workflow de Chat: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

async def generate_chat_title_service(message: str, session_id: str, user_id: str) -> str:
    """Gera um título curto e salva no histórico da sessão."""
    _update_activity(session_id)
    try:
        prompt = f"Gere um título muito curto (máximo 4 palavras) para uma conversa que começa com esta pergunta: '{message}'. Responda APENAS o título."
        response = await Settings.llm.acomplete(prompt)
        title = str(response).strip('"\'. ')
        
        # Salva o título no histórico visual
        _init_history(session_id, user_id)
        _chat_histories[session_id]["title"] = title
        
        return title
    except Exception as e:
        logger.error(f"Erro ao gerar título: {e}")
        return "Nova Conversa"

def get_user_chats_service(user_id: str) -> Dict[str, dict]:
    """Filtra e retorna todos os chats associados a um usuário específico, renovando a atividade."""
    _cleanup_inactive_sessions()
    user_chats = {}
    for sid, h in _chat_histories.items():
        if h["user_id"] == user_id:
            _update_activity(sid) # Renova o tempo de vida ao visualizar/carregar
            user_chats[sid] = {
                "title": h["title"],
                "messages": h["messages"],
                "sources": h["sources"]
            }
    return user_chats

def delete_chat_service(session_id: str):
    """Remove permanentemente uma sessão da memória do backend."""
    logger.info(f"[DELETE] Removendo sessão por solicitação: {session_id}")
    _session_contexts.pop(session_id, None)
    _chat_histories.pop(session_id, None)
    _last_activity.pop(session_id, None)
