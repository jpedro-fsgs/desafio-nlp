from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class RetrievalMode(str, Enum):
    LOCAL = "local"
    URL = "url"
    GCS = "gcs" # Novo modo para GCP Bucket

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1500, description="A pergunta deve ter entre 3 e 500 caracteres.")

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
    max_retrieval: int = 10
