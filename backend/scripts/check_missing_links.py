import re
import sqlite3
import os
from datetime import datetime

DB_PATH = "backend/data/aneel_legislacao2.db"
LINKS_FILE = "resultado_links.txt"

SIGLA_MAP = {
    "ren": ("REN", "Resolução Normativa"),
    "dsp": ("DSP", "Despacho"),
    "rea": ("REA", "Resolução Autorizativa"),
    "prt": ("PRT", "Portaria"),
    "reh": ("REH", "Resolução Homologatória"),
    "ina": ("INA", "Instrução Normativa"),
    "aaap": ("AAAP", "Ato Administrativo"),
    "adsp": ("ADSP", "Anexo de Despacho"),
    "area": ("AREA", "Anexo de Resolução Autorizativa"),
    "aprt": ("APRT", "Anexo de Portaria"),
    "areh": ("AREH", "Anexo de Resolução Homologatória"),
}

def infer_metadata(filename: str):
    filename = filename.lower()
    sigla, natureza = "OUTRO", "Documento"
    for prefix, (s, n) in SIGLA_MAP.items():
        if filename.startswith(prefix):
            sigla, natureza = s, n
            break
    return sigla, natureza

def register_missing_links():
    # 1. Extrair links do arquivo txt
    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    links = re.findall(r'https?://[^\s,]+?\.pdf', content)
    unique_links = sorted(list(set(links)))
    
    print(f"Total de links PDF únicos encontrados no TXT: {len(unique_links)}")

    # 2. Conectar ao SQLite e inserir faltantes
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted_count = 0
    
    for url in unique_links:
        # Verifica se a URL já existe
        cursor.execute("SELECT id FROM pdfs WHERE url = ?", (url,))
        if cursor.fetchone():
            continue
            
        filename = url.split("/")[-1].split("?")[0]
        sigla, natureza = infer_metadata(filename)
        
        # Inserção no controle do SQLite
        # registro_id = 0 para links órfãos/descobertos
        try:
            cursor.execute("""
                INSERT INTO pdfs (registro_id, tipo, url, arquivo, sigla, natureza, status_download, status_ingestao)
                VALUES (?, ?, ?, ?, ?, ?, 'pendente', 'pendente')
            """, (0, natureza, url, filename, sigla, natureza))
            inserted_count += 1
        except Exception as e:
            print(f"Erro ao inserir {url}: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"Novos links registrados no SQLite para download: {inserted_count}")

if __name__ == "__main__":
    register_missing_links()
