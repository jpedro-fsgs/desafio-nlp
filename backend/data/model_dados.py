from typing import Any, Dict, List

from pydantic import BaseModel, RootModel


class Pdf(BaseModel):
    tipo: str
    url: str
    arquivo: str
    baixado: bool


class Registros(BaseModel):
    numeracaoItem: str
    titulo: str
    autor: str | None
    material: str
    esfera: str | None
    situacao: str | None
    assinatura: str | None
    publicacao: str
    assunto: str | None
    ementa: str | None
    pdfs: List[Pdf]


class RegistroDiario(BaseModel):
    status: str
    registros: List[Registros]


class Model(RootModel[Any]):
    root: Dict[str, RegistroDiario]
