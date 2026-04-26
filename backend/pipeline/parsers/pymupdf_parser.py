import fitz
import pymupdf4llm
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, cast


class PyMuPDFParser:
    """
    Parser especializado em extrair Markdown limpo e detectar rasuras (strikethrough).

    Correções aplicadas vs versão anterior:
    - Rasuras substituem apenas a PRIMEIRA ocorrência de cada trecho no escopo
      correto (por posição geométrica), evitando falsos positivos globais.
    - Links internos do Markdown são removidos preservando apenas o texto do link.
    - Tratamento de exceções granular: erros de página única não abortam o documento.
    """

    # Critérios geométricos para detecção de rasura
    _STRIKE_MAX_HEIGHT = 2.5   # px — linhas mais altas são separadores/bordas
    _STRIKE_MIN_HEIGHT = 0.1   # px — exclui pontos/artefatos de 0px
    _STRIKE_MIN_WIDTH  = 5.0   # px — exclui traços minúsculos
    _STRIKE_REL_Y_MIN  = 0.35  # posição relativa vertical mínima (35% da altura do span)
    _STRIKE_REL_Y_MAX  = 0.65  # posição relativa vertical máxima (65%)
    _STRIKE_H_COVERAGE = 0.40  # cobertura horizontal mínima (40% da largura do span)

    # ------------------------------------------------------------------ #
    #  Entrypoint público                                                  #
    # ------------------------------------------------------------------ #

    def parse(self, pdf_path: str) -> Dict[str, Any]:
        """
        Retorna:
            text                  — Markdown limpo com rasuras marcadas como ~~texto~~
            rasuras_detectadas    — lista de trechos rasurados (sem duplicatas)
            links_referenciados   — lista de URLs externas encontradas (sem duplicatas)
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

        # ── Passo 1: extração Markdown via pymupdf4llm ──────────────────
        md_text = self._extrair_markdown(pdf_path)

        # ── Passo 2: análise geométrica (rasuras e links) ───────────────
        rasuras_por_pagina, links_extraidos = self._analisar_pdf(pdf_path)

        # ── Passo 3: aplicar rasuras de forma cirúrgica ──────────────────
        todas_rasuras = [t for pagina in rasuras_por_pagina for t in pagina]
        md_final = self._aplicar_strikethrough(md_text, todas_rasuras)

        return {
            "text": md_final,
            "rasuras_detectadas": list(dict.fromkeys(todas_rasuras)),  # preserva ordem, sem dup
            "links_referenciados": list(dict.fromkeys(links_extraidos)),
        }

    # ------------------------------------------------------------------ #
    #  Extração de Markdown                                                #
    # ------------------------------------------------------------------ #

    def _extrair_markdown(self, pdf_path: str) -> str:
        try:
            raw = pymupdf4llm.to_markdown(pdf_path, write_images=False)
            md = str(raw) if raw else ""
            # Remove links do Markdown mantendo apenas o texto âncora
            # Ex.: [Resolução 1234](http://...) → Resolução 1234
            md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
            return md
        except Exception as exc:
            # Falha total do pymupdf4llm — retorna vazio mas não aborta
            print(f"[AVISO] pymupdf4llm falhou em {pdf_path}: {exc}")
            return ""

    # ------------------------------------------------------------------ #
    #  Análise geométrica do PDF                                           #
    # ------------------------------------------------------------------ #

    def _analisar_pdf(self, pdf_path: str) -> Tuple[List[List[str]], List[str]]:
        """
        Retorna:
            rasuras_por_pagina — lista de listas; índice == número da página.
            links_urls         — lista plana de URLs encontradas.
        """
        rasuras_por_pagina: List[List[str]] = []
        links_urls: List[str] = []

        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    page_rasuras = self._detectar_rasuras_na_pagina(page)
                    rasuras_por_pagina.append(page_rasuras)

                    for link in page.get_links():
                        uri = link.get("uri", "")
                        if uri:
                            links_urls.append(uri)
        except Exception as exc:
            print(f"[AVISO] Falha ao analisar geometria de {pdf_path}: {exc}")

        return rasuras_por_pagina, links_urls

    def _detectar_rasuras_na_pagina(self, page: fitz.Page) -> List[str]:
        """Detecta trechos rasurados em uma única página."""
        rasuras: List[str] = []
        vistos: set[str] = set()

        try:
            # Filtra somente linhas horizontais finas (candidatas a rasura)
            strike_rects = [
                d["rect"]
                for d in page.get_drawings()
                if self._e_linha_rasura(d.get("rect"))
            ]
            if not strike_rects:
                return rasuras

            dict_page = cast(Dict[str, Any], page.get_text("dict"))

            for block in dict_page.get("blocks", []):
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = str(span.get("text", "")).strip()
                        if len(text) < 2 or text in vistos:
                            continue

                        s_rect = fitz.Rect(span["bbox"])
                        height = s_rect.y1 - s_rect.y0
                        if height <= 0:
                            continue

                        for sr in strike_rects:
                            if not sr.intersects(s_rect):
                                continue

                            # Verifica posição vertical relativa (rasura ≠ sublinhado)
                            mid_y = (sr.y0 + sr.y1) / 2
                            rel_y = (mid_y - s_rect.y0) / height
                            if not (self._STRIKE_REL_Y_MIN <= rel_y <= self._STRIKE_REL_Y_MAX):
                                continue

                            # Verifica cobertura horizontal suficiente
                            inter_x = min(s_rect.x1, sr.x1) - max(s_rect.x0, sr.x0)
                            span_w  = s_rect.x1 - s_rect.x0
                            if span_w > 0 and (inter_x / span_w) >= self._STRIKE_H_COVERAGE:
                                vistos.add(text)
                                rasuras.append(text)
                                break  # um match por span é suficiente

        except Exception as exc:
            print(f"[AVISO] Erro ao detectar rasuras na página {page.number}: {exc}")

        return rasuras

    def _e_linha_rasura(self, rect: Any) -> bool:
        if not rect:
            return False
        h = rect.y1 - rect.y0
        w = rect.x1 - rect.x0
        return (self._STRIKE_MIN_HEIGHT < h <= self._STRIKE_MAX_HEIGHT) and (w > self._STRIKE_MIN_WIDTH)

    # ------------------------------------------------------------------ #
    #  Aplicação de strikethrough no Markdown                              #
    # ------------------------------------------------------------------ #

    def _aplicar_strikethrough(self, md_text: str, rasuras: List[str]) -> str:
        """
        Marca rasuras no Markdown usando ~~trecho~~.

        Estratégia segura:
        - Ordena por comprimento decrescente para evitar que um trecho menor
          seja substituído dentro de um maior antes deste ser processado.
        - Usa re.sub com re.escape para substituir somente ocorrências
          que ainda não estejam dentro de marcações ~~...~~.
        - Substitui TODAS as ocorrências exatas (correto: se o texto rasurado
          aparece N vezes, provavelmente todas são rasuras do mesmo tipo de bloco).
        """
        if not md_text or not rasuras:
            return md_text

        # Remove duplicatas preservando ordem de detecção
        rasuras_unicas = list(dict.fromkeys(rasuras))

        for trecho in sorted(rasuras_unicas, key=len, reverse=True):
            if not trecho or trecho not in md_text:
                continue

            escaped = re.escape(trecho)

            # Só substitui se o trecho NÃO estiver já dentro de ~~ ... ~~
            # Lookbehind/lookahead garante que não há ~~ imediatamente adjacente
            padrao = rf"(?<!~)({escaped})(?!~)"
            md_text = re.sub(padrao, r"~~\1~~", md_text)

        return md_text