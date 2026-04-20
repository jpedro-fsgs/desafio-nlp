from typing import List
from pydantic import BaseModel
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

class RetrievalModeRequest(BaseModel):
    mode: RetrievalMode
