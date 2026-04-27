from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class RetrievalMode(str, Enum):
    LOCAL = "local"
    URL = "url"
    GCS = "gcs"

# --- Contrato de Retrieval Padronizado ---

class SourceModel(BaseModel):
    id: str = Field(description="Identificador único para deduplicação (ex: registro_id ou nome do arquivo)")
    title: str = Field(description="Título amigável para exibição no frontend")
    link: Optional[str] = Field(default=None, description="Link de acesso direto ao documento")
    tool_name: Optional[str] = Field(default=None, description="Ferramenta que gerou esta fonte")
    text: Optional[str] = Field(default=None, description="Trecho, ementa ou resumo do conteúdo")

class ToolResponseModel(BaseModel):
    text: Optional[str] = Field(default=None, description="O conteúdo em texto retornado pela busca")
    sources: List[SourceModel] = Field(default_factory=list, description="Lista padronizada de fontes")

    def __str__(self):
        """Garante que o LLM receba o texto otimizado ao invés do dump JSON do modelo."""
        return self.text or "Nenhum conteúdo textual retornado."

# --- Requisições e Respostas ---

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1500, description="A pergunta deve ter entre 3 e 1500 caracteres.")

class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[SourceModel]

class ConfigSettingsRequest(BaseModel):
    mode: Optional[RetrievalMode] = None
    top_k: Optional[int] = Field(None, ge=1, le=10, description="Número de documentos a recuperar (máximo 10)")

class ConfigResponse(BaseModel):
    status: str
    retrieval_mode: RetrievalMode
    similarity_top_k: int
    max_retrieval: int = 10

class RetrievalModeRequest(BaseModel):
    mode: RetrievalMode

# --- Novos Schemas para o Chat Stateful ---

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="ID único do usuário.")
    session_id: str = Field(..., description="ID único da sessão do chat no frontend.")
    message: str = Field(..., min_length=1, max_length=2000, description="A mensagem do usuário.")

class TitleRequest(BaseModel):
    user_id: str = Field(..., description="ID único do usuário.")
    session_id: str = Field(..., description="ID único da sessão do chat no frontend.")
    message: str = Field(..., description="A primeira mensagem do usuário.")

class TitleResponse(BaseModel):
    title: str
