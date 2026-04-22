from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class RetrievalMode(str, Enum):
    LOCAL = "local"
    URL = "url"

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[dict]

class ConfigSettingsRequest(BaseModel):
    mode: Optional[RetrievalMode] = None
    top_k: Optional[int] = Field(None, ge=1, le=10, description="Número de documentos a recuperar (máximo 10)")

class ConfigResponse(BaseModel):
    status: str
    retrieval_mode: RetrievalMode
    similarity_top_k: int
    max_retrieval: int = 10 # Limite fixo informado na resposta
