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

async def handle_chat_stream(user_input: str, chat_id: str, chat_column):
    """Lida com o stream de forma limpa e profissional."""
    chat = st.session_state.chats[chat_id]
    chat["messages"].append({"role": "user", "content": user_input})
    
    if len(chat["messages"]) == 1:
        asyncio.create_task(generate_title(chat_id, user_input))

    headers = {"access_token": str(API_KEY or ""), "Content-Type": "application/json"}
    payload = {"session_id": chat_id, "message": user_input}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            with chat_column:
                # 1. Indicador dinâmico de pensamento (Placeholder)
                status_placeholder = st.empty()
                status_placeholder.markdown(":material/sync: *Processando consulta regulatória...*")
                
                full_response = ""
                
                async with client.stream("POST", f"{BACKEND_URL}/chat/stream", json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        status_placeholder.error("Falha na comunicação com o backend.")
                        return

                    with st.chat_message("assistant"):
                        response_placeholder = st.empty()
                        
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "): continue
                            data = json.loads(line.replace("data: ", ""))
                            
                            if data["type"] == "status":
                                # Atualiza o texto do indicador dinâmico
                                status_placeholder.markdown(f":material/search: *{data['content']}...*")
                            
                            elif data["type"] == "token":
                                # Remove o indicador assim que a resposta começa
                                status_placeholder.empty()
                                full_response += data["content"]
                                response_placeholder.markdown(full_response)
                            
                            elif data["type"] == "sources":
                                chat["sources"] = data["content"]

                chat["messages"].append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"Erro: {e}")

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
        # Título usando a classe CSS que evita cortes
        st.markdown(f'<div class="chat-title">{chat_data["title"]}</div>', unsafe_allow_html=True)
        
        # Área de mensagens
        for msg in chat_data["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    with col_info:
        st.markdown('<div class="context-panel">', unsafe_allow_html=True)
        st.subheader(":material/menu_book: Fontes", anchor=False)
        if not chat_data["sources"]:
            st.caption("Fontes serão listadas aqui.")
        else:
            for src in chat_data["sources"][:5]:
                with st.expander(src.get('file_name', 'Documento'), expanded=True):
                    st.caption(src.get('ementa', 'Sem ementa'))
                    if 'url' in src:
                        st.link_button("Abrir PDF", src['url'], icon=":material/open_in_new:", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # INPUT GLOBAL: Fixado na base da página por padrão do Streamlit
    if prompt := st.chat_input("Escreva sua pergunta aqui..."):
        # Mostra a pergunta do usuário imediatamente
        with col_chat:
            with st.chat_message("user"):
                st.markdown(prompt)
        
        # Dispara o processamento e stream
        asyncio.run(handle_chat_stream(prompt, cur_id, col_chat))
        st.rerun()
else:
    st.info("Inicie uma consulta.")
