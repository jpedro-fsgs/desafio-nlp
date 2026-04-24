import sqlite3
import os
import re
from pypdf import PdfReader
from collections import Counter

DB_PATH = "data/aneel_legislacao.db"
DOWNLOADS_DIR = "data/downloads"

def extract_links_from_pdf(pdf_path):
    links = []
    text_urls = []
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            # 1. Extrair links de anotações (hyperlinks clicáveis)
            if "/Annots" in page:
                annots = page["/Annots"]
                for annot in annots:
                    obj = annot.get_object()
                    if obj and "/A" in obj and "/URI" in obj["/A"]:
                        uri = obj["/A"]["/URI"]
                        if isinstance(uri, str):
                            links.append(uri)
                        elif hasattr(uri, "get_object"):
                            links.append(str(uri.get_object()))

            # 2. Extrair URLs do texto (regex simples)
            text = page.extract_text()
            if text:
                # Regex para encontrar URLs típicas
                urls = re.findall(r'(https?://[^\s\"\'\<\>]+)', text)
                text_urls.extend(urls)
                
    except Exception as e:
        # Silencioso para não poluir o terminal durante o loop em massa
        pass
    
    return links, text_urls

def analisar_links_revogadas():
    if not os.path.exists(DB_PATH):
        print(f"Erro: Banco de dados {DB_PATH} não encontrado.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Buscar arquivos de registros revogados
    print("Buscando registros revogados no banco de dados...")
    cursor.execute("""
        SELECT p.arquivo, r.titulo
        FROM registros r
        JOIN pdfs p ON r.id = p.registro_id
        WHERE r.situacao = 'REVOGADA' AND p.arquivo LIKE '%.pdf'
    """)
    records = cursor.fetchall()
    conn.close()

    total_records = len(records)
    print(f"Total de PDFs revogados para analisar: {total_records}")
    
    todos_links_anotacao = []
    todos_links_texto = []
    arquivos_com_link = 0
    analisados_sucesso = 0

    for i, (arquivo, titulo) in enumerate(records):
        caminho = os.path.join(DOWNLOADS_DIR, arquivo)
        if os.path.exists(caminho):
            links_annot, links_text = extract_links_from_pdf(caminho)
            if links_annot or links_text:
                arquivos_com_link += 1
                todos_links_anotacao.extend(links_annot)
                todos_links_texto.extend(links_text)
            analisados_sucesso += 1
                
        if (i + 1) % 100 == 0:
            print(f"Processados {i + 1}/{total_records}...")

    # Compilar resultados
    print(f"\n--- Resultados da Análise ---")
    print(f"PDFs analisados fisicamente: {analisados_sucesso}")
    print(f"PDFs que contêm algum link: {arquivos_com_link}")
    
    output_lines = []
    output_lines.append(f"Análise realizada em: {total_records} documentos revogados.")
    output_lines.append(f"Documentos com links encontrados: {arquivos_com_link}")
    output_lines.append("\nTOP 20 LINKS EM ANOTAÇÕES (Hyperlinks clicáveis):")
    for link, count in Counter(todos_links_anotacao).most_common(20):
        output_lines.append(f"  - {count:3d} ocorrências: {link}")
        
    output_lines.append("\nTOP 20 URLs ENCONTRADAS NO TEXTO:")
    for link, count in Counter(todos_links_texto).most_common(20):
        output_lines.append(f"  - {count:3d} ocorrências: {link}")

    # Exibir no terminal
    print("\n".join(output_lines))

    # Salvar em arquivo
    with open("resultado_links.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print(f"\n[OK] Análise salva em 'resultado_links.txt'")

if __name__ == "__main__":
    analisando = analisar_links_revogadas()
