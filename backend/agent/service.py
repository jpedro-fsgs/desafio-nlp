import json
from typing import Dict, AsyncGenerator
from llama_index.core.agent.workflow import FunctionAgent, ToolCall, AgentStream, ToolCallResult
from llama_index.core.workflow import Context
from agent.tools import get_agent_tools
from models import ToolResponseModel, SourceModel
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
    
    logger.info(f"[CHAT] Iniciando workflow para sessão {session_id}. Mensagem: '{message[:50]}...'")

    # 1. Recupera as Ferramentas do Agente
    tools = get_agent_tools()
    if not tools:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Erro ao inicializar ferramentas do agente.'})}\n\n"
        return

    # 2. Inicializa o Agente de Workflow
    agent = FunctionAgent(
        tools=tools,
        llm=Settings.llm,
        system_prompt=(
            "Você é um assistente jurídico especializado na regulação do setor elétrico brasileiro (ANEEL). "
            "Sua estratégia de busca deve seguir estes passos:\n"
            "1. SEMPRE comece pesquisando na ferramenta 'pesquisar_registros_aneel' e 'pesquisar_documentos_pdf_aneel' para identificar as normas, portarias ou resoluções pertinentes e seus status.\n"
            "2. Se precisar de detalhes técnicos, tabelas, cálculos ou fundamentações profundas específicas contidas nos anexos e documentos integrais, utilize a ferramenta 'pesquisar_documentos_pdf_aneel'.\n"
            "3. Se você já souber o nome exato de um arquivo (ex: 'ren20211000.pdf'), prefira usar 'ler_documento_completo_direto' para ler o texto integral imediatamente.\n\n"
            "4. A ferramenta 'pesquisar_documentos_pdf_aneel' somente retorna trechos dos documentos, para recuperação completa utilize 'ler_documento_completo_direto'.\n\n"
            "5. Alguns documentos são revogados por outros, e os trechos revogados são ~~rasurados~~. Se encontrar um trecho riscado, busque a norma que o revogou para entender o contexto atual.\n\n"
            "6. Os arquivos originais dos documentos citados no texto estão disponíveis na ferramenta 'ler_documento_completo_direto' e devem ser consultados para garantir a precisão da resposta, especialmente em casos de revogação.\n\n"
            "Sua resposta final deve ser fundamentada, citando os números das normas e resoluções encontradas. "
            "Caso ocorra algum erro técnico em uma ferramenta, informe ao usuário mas tente alternativas se possível."
        )
    )

    # 3. Recupera o contexto da sessão (contém o histórico)
    ctx = _get_context(session_id, agent)

    # 4. Executa o Workflow com streaming de eventos e limite de segurança aumentado
    handler = agent.run(ctx=ctx, user_msg=message, max_steps=40)

    try:
        # Feedback inicial imediato
        yield f"data: {json.dumps({'type': 'status', 'content': 'Agente iniciando raciocínio...'})}\n\n"

        async for ev in handler.stream_events():
            # Evento de Chamada de Ferramenta
            if isinstance(ev, ToolCall):
                msg = f"Agente decidiu pesquisar: {ev.tool_name}"
                yield f"data: {json.dumps({'type': 'status', 'content': msg})}\n\n"
            
            # Evento de Resultado da Ferramenta (Extração de fontes em tempo real via Contrato Pydantic)
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
                            "link": m.get('pdf_url_acesso'),
                            "tool_name": ev.tool_name
                        })
                
                # Caso 3: Fallback para strings simples (Garante que nada seja perdido)
                else:
                    out_str = str(output)
                    if "LINK" in out_str.upper():
                        import re
                        link_match = re.search(r"(https?://\S+)", out_str)
                        if link_match:
                            sources_payload.append({
                                "id": "extracted_link",
                                "title": "Documento Citado",
                                "link": link_match.group(1),
                                "tool_name": ev.tool_name
                            })
                
                if sources_payload:
                    yield f"data: {json.dumps({'type': 'sources', 'content': sources_payload})}\n\n"
                
                yield f"data: {json.dumps({'type': 'status', 'content': 'Analisando resultados da pesquisa...'})}\n\n"
            
            # Evento de Token de Resposta
            elif isinstance(ev, AgentStream):
                if ev.delta:
                    yield f"data: {json.dumps({'type': 'token', 'content': ev.delta})}\n\n"
                else:
                    # Envia um feedback de pensamento quando o token for vazio
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Agente está pensando...'})}\n\n"
        
        # Aguarda a conclusão total do workflow
        await handler
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        logger.info(f"[CHAT] Workflow concluído para sessão {session_id}.")

    except Exception as e:
        logger.error(f"Erro no Workflow de Chat: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

async def generate_chat_title_service(message: str) -> str:
    """Gera um título curto para a sessão de chat baseado na primeira mensagem."""
    try:
        prompt = f"Gere um título muito curto (máximo 4 palavras) para uma conversa que começa com esta pergunta: '{message}'. Responda APENAS o título."
        response = await Settings.llm.acomplete(prompt)
        return str(response).strip('"\'. ')
    except Exception as e:
        logger.error(f"Erro ao gerar título: {e}")
        return "Nova Conversa"
