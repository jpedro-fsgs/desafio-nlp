import os
# Define limites de thread ANTES de qualquer import de biblioteca pesada (torch, fitz, docling)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import argparse
import json
import time
from pathlib import Path
from typing import cast
import multiprocessing as mp
import torch
from tqdm import tqdm
import fitz  # PyMuPDF

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice

# --- CONFIGURAÇÃO DE SELEÇÃO MANUAL ---
# Se esta lista contiver nomes de arquivos, o script processará APENAS eles.
# Exemplo: SPECIFIC_FILES = ["dsp20162086ti.pdf", "dsp20162082ti.pdf"]
SPECIFIC_FILES = []

# --- LÓGICA FASE 1: PyMuPDF (CPU Bound) ---

def extract_strikethroughs_from_pdf(pdf_path: str) -> tuple:
    """
    Worker da Fase 1: Identifica textos sob linhas/retângulos horizontais finos.
    Retorna uma tupla (nome_arquivo, [lista_de_textos_rasurados]).
    """
    strikethroughs = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                drawings = page.get_drawings()
                
                # Detecta linhas/retângulos horizontais (independente de cor)
                h_lines = []
                for d in drawings:
                    if not isinstance(d, dict): continue
                    rect = d.get("rect")
                    if rect:
                        h = rect.y1 - rect.y0
                        w = rect.x1 - rect.x0
                        # Filtra apenas elementos horizontais finos
                        if 0 < h <= 3 and w > 10:
                            h_lines.append(rect)
                
                if not h_lines: continue
                
                # Cruza as linhas com os blocos de texto
                dict_page = cast(dict, page.get_text("dict"))
                for block in dict_page.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            s_rect = fitz.Rect(span["bbox"])
                            text = span.get("text", "").strip()
                            if not text or len(text) < 3: continue
                            
                            for hl in h_lines:
                                # REJEIÇÃO RÁPIDA: Se as caixas não se tocam, pule imediatamente
                                if not s_rect.intersects(hl):
                                    continue
                                    
                                # Lógica matemática refinada: cruza o centro vertical e cobre largura
                                mid_y = (s_rect.y0 + s_rect.y1) / 2
                                if hl.y0 <= mid_y <= hl.y1:
                                    intersecao_x = min(s_rect.x1, hl.x1) - max(s_rect.x0, hl.x0)
                                    if intersecao_x > (s_rect.x1 - s_rect.x0) * 0.4:
                                        strikethroughs.append(text)
                                        break # Já marcou este span
                                        
    except Exception as e:
        print(f"\n[AVISO] Erro PyMuPDF em {Path(pdf_path).name}: {e}")
        
    return (os.path.basename(pdf_path), list(set(strikethroughs)))

# --- LÓGICA FASE 2: Docling (GPU Bound) ---

def main():
    parser = argparse.ArgumentParser(description="Pipeline Otimizado: PyMuPDF (CPU) + Docling (GPU)")
    parser.add_argument("--limit", type=int, default=0, help="Limite de PDFs a processar")
    parser.add_argument("--process-images", action="store_true", help="Ativar extração de imagens no Docling")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="Número de workers para Fase 1")
    parser.add_argument("--max-size", type=float, default=1.0, help="Tamanho máximo do PDF em MB (Padrão: 1.0)")
    args = parser.parse_args()

    downloads_dir = Path("data/downloads")
    output_dir = Path("data/parsed_docs")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not downloads_dir.exists():
        print(f"[ERRO] Pasta {downloads_dir} não encontrada.")
        return

    # Escolha de arquivos: Prioriza a lista SPECIFIC_FILES se não estiver vazia
    if SPECIFIC_FILES:
        all_pdfs = [downloads_dir / f for f in SPECIFIC_FILES if (downloads_dir / f).exists()]
        if not all_pdfs:
            print(f"[ERRO] Nenhum dos arquivos especificados em SPECIFIC_FILES foi encontrado em {downloads_dir}.")
            return
    else:
        # Comportamento padrão: busca todos os PDFs da pasta
        all_pdfs = sorted(list(downloads_dir.glob("*.pdf")))

    pdf_paths = []
    
    max_bytes = args.max_size * 1024 * 1024
    for p in all_pdfs:
        if p.stat().st_size <= max_bytes:
            pdf_paths.append(p)
        
    if args.limit > 0:
        pdf_paths = pdf_paths[:args.limit]

    if not pdf_paths:
        print(f"[!] Nenhum PDF encontrado (Limite: {args.max_size}MB).")
        return

    print("=" * 60)
    print(f"[*] Total de PDFs: {len(pdf_paths)} (Filtro: {args.max_size}MB)")
    print(f"[*] Fase 1 (CPU): PyMuPDF com {args.workers} workers (Fast-Fail ativo)")
    print(f"[*] Fase 2 (GPU): Docling com convert_all (OCR Desativado)")
    print("=" * 60)

    # --- FASE 1: EXTRAÇÃO DE RASURAS (PARALELISMO CPU) ---
    strikethroughs_map = {}
    paths_str = [str(p) for p in pdf_paths]
    
    start_fase1 = time.time()
    with mp.Pool(args.workers) as pool:
        for filename, items in tqdm(pool.imap_unordered(extract_strikethroughs_from_pdf, paths_str), 
                                     total=len(paths_str), 
                                     desc="Fase 1: Rasuras (Fitz)", 
                                     dynamic_ncols=True):
            if items:
                strikethroughs_map[filename] = items
    
    print(f"[*] Fase 1 concluída em {time.time() - start_fase1:.2f}s.")

    # --- FASE 2: CONVERSÃO DOCLING (LOTE GPU) ---
    print("\n[*] Inicializando Docling na GPU...")
    device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.CPU
    acc_opts = AcceleratorOptions(device=device)
    
    # Otimização: do_ocr=False para ganho massivo de velocidade em PDFs digitais
    p_opts = PdfPipelineOptions(
        do_ocr=False,
        do_table_structure=True,
        generate_page_images=args.process_images,
        accelerator_options=acc_opts
    )
    
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=p_opts)}
    )

    start_fase2 = time.time()
    success_count = 0
    error_count = 0
    
    with tqdm(total=len(pdf_paths), desc="Fase 2: Markdown (Docling)", dynamic_ncols=True) as pbar:
        for result in converter.convert_all(paths_str):
            filename = os.path.basename(result.input.file)
            try:
                # Extrai o Markdown base
                md = result.document.export_to_markdown()
                
                # Aplica as rasuras da Fase 1
                if filename in strikethroughs_map:
                    for text_to_strike in strikethroughs_map[filename]:
                        if text_to_strike in md:
                            md = md.replace(text_to_strike, f"~~{text_to_strike}~~")
                
                # Salva o resultado
                out_path = output_dir / f"{filename}.md"
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md)
                
                success_count += 1
            except Exception as e:
                print(f"\n[ERRO] Falha ao processar {filename}: {e}")
                error_count += 1
            
            pbar.update(1)

    total_time = time.time() - start_fase1
    print("\n" + "=" * 60)
    print(f"[*] Pipeline Concluído em {total_time:.2f}s")
    print(f"[*] Sucessos: {success_count} | Erros: {error_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
