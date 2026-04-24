import streamlit as st
import httpx
import json
import uuid
import asyncio

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="ANEEL RAG - Legislação Inteligente",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ ANEEL RAG - Consulta Legislativa")
st.markdown("---")

# --- ESTADO DA SESSÃO ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- CONFIGURAÇÕES DO BACKEND ---
BACKEND_URL = "http://localhost:8000"
# Idealmente, isto viria de uma variável de ambiente no deploy
API_KEY = "7BTpvVGhsbtKuU30jRrsVQtmIbWAvZEtNZHOG5ZVs4Y" 

# --- INTERFACE DE CHAT ---
# Exibir mensagens anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- FUNÇÃO DE STREAMING ---
async def stream_chat(user_input: str):
    payload = {
        "session_id": st.session_state.session_id,
        "message": user_input
    }
    headers = {
        "access_token": API_KEY,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Exibir um status placeholder para pensamentos do agente
            status_placeholder = st.empty()
            with status_placeholder.status("⚙️ Pensando...", expanded=True) as status_box:
                full_response = ""
                response_placeholder = st.empty()
                
                async with client.stream("POST", f"{BACKEND_URL}/chat/stream", json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        st.error(f"Erro na API: {response.status_code}")
                        return

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        
                        try:
                            data = json.loads(line.replace("data: ", ""))
                            
                            # Lidar com mensagens de STATUS (Pensamento do Agente)
                            if data["type"] == "status":
                                status_box.write(f"🔹 {data['content']}")
                            
                            # Lidar com TOKENS da resposta
                            elif data["type"] == "token":
                                # Uma vez que o primeiro token chega, podemos mudar o status
                                status_box.update(label="✅ Resposta fundamentada encontrada!", state="complete", expanded=False)
                                
                                token = data["content"]
                                full_response += token
                                response_placeholder.markdown(full_response + "▌")
                                
                            elif data["type"] == "error":
                                st.error(f"Erro no processamento: {data['content']}")
                                
                        except json.JSONDecodeError:
                            continue

                response_placeholder.markdown(full_response)
                return full_response

        except Exception as e:
            st.error(f"Falha na conexão com o backend: {e}")
            return None

# --- INPUT DO USUÁRIO ---
if prompt := st.chat_input("Ex: Quais as regras de tarifas para 2016?"):
    # Adicionar mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Gerar resposta via streaming
    with st.chat_message("assistant"):
        response = asyncio.run(stream_chat(prompt))
        if response:
            st.session_state.messages.append({"role": "assistant", "content": response})

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://www.aneel.gov.br/images/logo_aneel.png", width=200)
    st.info(f"Sessão Ativa: {st.session_state.session_id[:8]}")
    if st.button("Limpar Chat"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()
    
    st.markdown("### Configurações")
    st.caption("A API utiliza Small-to-Big Retrieval (Qdrant + PDF Integral)")
