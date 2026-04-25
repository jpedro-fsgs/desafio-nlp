import asyncio
import json
from typing import Dict, AsyncGenerator
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core.agent.workflow import FunctionAgent, ToolCall, AgentStream, ToolCallResult
from llama_index.core.workflow import Context
from qdrant_service import get_aneel_query_engine
from config import Settings, logger

# --- GERENCIAMENTO DE CONTEXTO (SESSÕES V0.14) ---
# session_id -> Context
_session_contexts: Dict[str, Context] = {}

def _get_context(session_id: str, agent: FunctionAgent) -> Context:
    """Recupera ou cria um novo contexto de workflow para a sessão."""
    if session_id not in _session_contexts:
        # No v0.14, o Context mantém o estado da conversa e variáveis do workflow
        _session_contexts[session_id] = Context(agent)
    return _session_contexts[session_id]

# --- SERVIÇO DO AGENTE ---
async def astream_agent_chat(session_id: str, message: str) -> AsyncGenerator[str, None]:
    """Orquestra o chat streaming usando o novo paradigma de Workflow do LlamaIndex v0.14."""
    
    # 1. Configura a Ferramenta de Busca
    query_engine = get_aneel_query_engine()
    if not query_engine:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Erro ao inicializar motor de busca.'})}\n\n"
        return

    tool = QueryEngineTool(
        query_engine=query_engine,
        metadata=ToolMetadata(
            name="pesquisar_legislacao_aneel",
            description="Use para buscar detalhes técnicos, resoluções, despachos e normas da ANEEL. Use obrigatoriamente se a pergunta for sobre regulação elétrica."
        )
    )

    # 2. Inicializa o Agente de Workflow
    # Nota: FunctionAgent herda de Workflow no v0.14
    agent = FunctionAgent(
        tools=[tool],
        llm=Settings.llm,
        system_prompt=(
            "Você é um assistente jurídico da ANEEL. "
            "Sua missão é ajudar usuários a entenderem a regulação do setor elétrico brasileiro. "
            "Se a pergunta for sobre normas, use a ferramenta de pesquisa imediatamente."
        )
    )

    # 3. Recupera o contexto da sessão (contém o histórico)
    ctx = _get_context(session_id, agent)

    # 4. Executa o Workflow com streaming de eventos
    handler = agent.run(ctx=ctx, user_msg=message)

    try:
        async for ev in handler.stream_events():
            # Evento de Chamada de Ferramenta
            if isinstance(ev, ToolCall):
                msg = f"Agente decidiu pesquisar: {ev.tool_name}"
                yield f"data: {json.dumps({'type': 'status', 'content': msg})}\n\n"
            
            # Evento de Resultado da Ferramenta (Extração de fontes em tempo real)
            elif isinstance(ev, ToolCallResult):
                raw = getattr(ev.tool_output, 'raw_output', None)
                if raw is not None and hasattr(raw, 'source_nodes'):
                    sources = [node.node.metadata for node in raw.source_nodes]
                    yield f"data: {json.dumps({'type': 'sources', 'content': sources})}\n\n"
            
            # Evento de Token de Resposta
            elif isinstance(ev, AgentStream):
                yield f"data: {json.dumps({'type': 'token', 'content': ev.delta})}\n\n"
        
        # Aguarda a conclusão total do workflow
        await handler
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    except Exception as e:
        logger.error(f"Erro no Workflow de Chat: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
