import streamlit as st
import httpx
import json
import uuid
import asyncio
import os
import dotenv
from typing import List, Dict

# Carregar variáveis de ambiente
dotenv.load_dotenv()

# --- CONFIGURAÇÃO DE AMBIENTE ---
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY")

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="ANEEL - Consulta Legislativa",
    page_icon=":material/bolt:",
    layout="wide",
)

# Estilos CSS Profissionais
st.markdown("""
    <style>
    /* Estabilidade do Layout e Margens */
    .block-container { 
        padding-top: 2rem !important; 
        padding-bottom: 6rem !important; 
        padding-left: 5rem !important; 
        padding-right: 5rem !important; 
        max-width: 1400px !important; 
    }
    
    /* Título do Chat - Garantir espaço e evitar cortes */
    .chat-title {
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        line-height: 1.5 !important;
        padding-top: 10px !important;
        padding-bottom: 10px !important;
        margin-bottom: 1rem !important;
        color: var(--text-color);
        display: block !important;
        overflow: visible !important;
    }

    /* Design de Mensagens Minimalista */
    .stChatMessage { 
        border-bottom: 1px solid var(--border-color) !important; 
        border-radius: 0px !important;
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
        background-color: transparent !important;
    }
    
    /* Ocultar Avatares e Ícones padrão */
    [data-testid="stChatMessageAvatar"] { display: none !important; }
    .stChatMessage { padding-left: 0px !important; }

    /* Painel de Contexto (Coluna Direita) - Ajuste de Overflow */
    .context-panel {
        padding: 1.5rem;
        background-color: var(--secondary-background-color);
        border-radius: 12px;
        border: 1px solid var(--border-color);
        margin-top: 1rem;
    }
    
    /* Botões da Sidebar - Ajuste para títulos longos */
    .stSidebar .stButton button {
        text-align: left !important;
        display: block !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZAÇÃO DO ESTADO ---
if "chats" not in st.session_state:
    st.session_state.chats = {}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

def create_new_chat():
    new_id = str(uuid.uuid4())
    st.session_state.chats[new_id] = {"title": "Nova Consulta", "messages": [], "sources": []}
    st.session_state.current_chat_id = new_id

if not st.session_state.chats:
    create_new_chat()
if st.session_state.current_chat_id not in st.session_state.chats:
    st.session_state.current_chat_id = next(iter(st.session_state.chats))

# --- AUXILIARES ---
async def generate_title(chat_id: str, first_msg: str):
    if not API_KEY: return
    try:
        async with httpx.AsyncClient() as client:
            headers = {"access_token": str(API_KEY)}
            resp = await client.post(f"{BACKEND_URL}/chat/title", json={"message": first_msg}, headers=headers)
            if resp.status_code == 200:
                st.session_state.chats[chat_id]["title"] = resp.json()["title"]
    except Exception: pass

def render_sources_ui(container, sources):
    """Renderiza os blocos de fontes padronizados (usado para atualizações em tempo real)."""
    with container.container():
        if not sources:
            st.caption("Fontes serão listadas aqui conforme a pesquisa.")
        else:
            st.markdown('<div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">', unsafe_allow_html=True)
            seen_ids = set()
            
            for src in sources[:20]: # Mostra até 20 fontes
                source_id = src.get('id')
                title = src.get('title', 'Documento')
                link = src.get('link')
                summary = src.get('text')
                
                # Deduplicação visual robusta baseada no ID do contrato
                if source_id in seen_ids: continue
                seen_ids.add(source_id)

                if link:
                    # Se for link, mostra apenas o botão de acesso (sem resumo/expander)
                    st.link_button(
                        title, 
                        link, 
                        icon=":material/description:", 
                        use_container_width=True,
                        help=f"Abrir documento original"
                    )
                else:
                    # Se não for link, mostra um expander com a ementa completa
                    with st.expander(title, icon=":material/info:"):
                        if summary:
                            st.markdown(f"**Ementa/Resumo:**\n\n{summary}")
                        else:
                            st.caption("Detalhes não disponíveis para este registro.")
            st.markdown('</div>', unsafe_allow_html=True)

async def handle_chat_stream(user_input: str, chat_id: str, chat_column, sources_placeholder):
    """Lida com o stream e atualiza a UI de fontes em tempo real usando o novo contrato."""
    chat = st.session_state.chats[chat_id]
    chat["messages"].append({"role": "user", "content": user_input})
    
    # Limpa fontes para a nova consulta
    chat["sources"] = [] 
    
    if len(chat["messages"]) == 1:
        asyncio.create_task(generate_title(chat_id, user_input))

    headers = {"access_token": str(API_KEY or ""), "Content-Type": "application/json"}
    payload = {"session_id": chat_id, "message": user_input}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            with chat_column:
                status_placeholder = st.empty()
                status_placeholder.markdown(":material/sync: *Processando consulta...*")
                
                full_response = ""
                
                async with client.stream("POST", f"{BACKEND_URL}/chat/stream", json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        status_placeholder.error("Falha na comunicação com o backend.")
                        return

                    with st.chat_message("assistant"):
                        response_placeholder = st.empty()
                        
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "): continue
                            data_raw = line.replace("data: ", "")
                            if not data_raw: continue
                            
                            data = json.loads(data_raw)
                            
                            if data["type"] == "status":
                                status_placeholder.markdown(f":material/search: *{data['content']}...*")
                            
                            elif data["type"] == "token":
                                if data["content"]: # Esconde status quando tokens reais chegam
                                    status_placeholder.empty()
                                full_response += data["content"]
                                response_placeholder.markdown(full_response)
                            
                            elif data["type"] == "sources":
                                # ACUMULA E DEDUPLICA FONTES VIA CONTRATO FORTE (ID)
                                new_sources = data["content"]
                                for ns in new_sources:
                                    if not any(s.get('id') == ns.get('id') for s in chat["sources"]):
                                        chat["sources"].append(ns)
                                
                                # ATUALIZA UI EM TEMPO REAL NO PAINEL LATERAL
                                render_sources_ui(sources_placeholder, chat["sources"])

                chat["messages"].append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"Erro no streaming: {e}")

# --- INTERFACE PRINCIPAL ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/1/1f/Aneel.png", width=160)
    st.title("Histórico")
    if st.button("Nova Consulta", icon=":material/add:", use_container_width=True):
        create_new_chat()
        st.rerun()
    st.divider()
    for chat_id in list(st.session_state.chats.keys()):
        chat_data = st.session_state.chats[chat_id]
        cols = st.columns([0.8, 0.2])
        with cols[0]:
            if st.button(chat_data['title'], key=f"sel_{chat_id}", use_container_width=True, 
                         type="primary" if chat_id == st.session_state.current_chat_id else "secondary"):
                st.session_state.current_chat_id = chat_id
                st.rerun()
        with cols[1]:
            if st.button(":material/delete:", key=f"del_{chat_id}"):
                del st.session_state.chats[chat_id]
                if st.session_state.current_chat_id == chat_id:
                    st.session_state.current_chat_id = next(iter(st.session_state.chats)) if st.session_state.chats else None
                st.rerun()

# Layout Principal
cur_id = st.session_state.current_chat_id
if cur_id:
    chat_data = st.session_state.chats[cur_id]
    col_chat, col_info = st.columns([0.72, 0.28], gap="large")
    
    with col_chat:
        st.markdown(f'<div class="chat-title">{chat_data["title"]}</div>', unsafe_allow_html=True)
        for msg in chat_data["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    with col_info:
        st.markdown('<div class="context-panel">', unsafe_allow_html=True)
        st.subheader(":material/menu_book: Fontes", anchor=False)
        
        # Placeholder para atualização dinâmica (fundamental para streaming interativo)
        sources_placeholder = st.empty()
        
        # Renderiza estado persistido (importante para recarregar histórico)
        render_sources_ui(sources_placeholder, chat_data["sources"])
        
        st.markdown('</div>', unsafe_allow_html=True)

    if prompt := st.chat_input("Escreva sua pergunta aqui..."):
        with col_chat:
            with st.chat_message("user"):
                st.markdown(prompt)
        
        # Agora passamos o sources_placeholder para a função de stream
        asyncio.run(handle_chat_stream(prompt, cur_id, col_chat, sources_placeholder))
        st.rerun()
else:
    st.info("Inicie uma consulta.")
