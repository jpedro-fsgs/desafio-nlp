import sqlite3
import requests
import os
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
DB_NAME = "aneel_legislacao.db"
DOWNLOAD_DIR = "downloads"
SLEEP_TIME = 1.0  # Tempo entre requisições (Cloudflare costuma aceitar ~1 req/s)
MAX_CONSECUTIVE_ERRORS = 5  # Para se houver N erros seguidos (bloqueio provável)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.aneel.gov.br/',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}

def download_pdfs(limit=None):
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    query = "SELECT id, url, arquivo FROM pdfs WHERE status_download != 'sucesso'"
    if limit:
        query += f" LIMIT {limit}"
        
    cursor.execute(query)
    pending_pdfs = cursor.fetchall()

    if not pending_pdfs:
        print("Nenhum PDF pendente.")
        conn.close()
        return

    print(f"Iniciando tentativa para {len(pending_pdfs)} PDFs.")

    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Simula visita à home para pegar cookies de sessão/cloudflare
    try:
        print("Acessando página inicial para inicializar sessão...")
        session.get("https://www.aneel.gov.br/", timeout=15)
        time.sleep(2)
    except Exception as e:
        print(f"Aviso: Não foi possível acessar a home: {e}")

    consecutive_errors = 0

    for pdf_id, url, filename in pending_pdfs:
        # Limpa espaços em branco extras no início ou fim
        url = url.strip()
        if filename:
            filename = filename.strip()
        
        # Define um nome de arquivo se estiver vazio
        if not filename:
            filename = url.split("/")[-1].split("?")[0]

        # Pula se não for PDF (zip, html, etc)
        if not filename.lower().endswith(".pdf"):
            print(f"PULANDO (Não é PDF): {filename}")
            continue
        
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"\n[!] PARANDO: {consecutive_errors} erros consecutivos. Possível bloqueio ou instabilidade.")
            break

        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)

        if not filename:
            filename = url.split("/")[-1]
            
        local_path = os.path.join(DOWNLOAD_DIR, filename)
        
        # Pula se já existe
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
             cursor.execute("UPDATE pdfs SET status_download = 'sucesso', data_download = ? WHERE id = ?", 
                           (datetime.now().isoformat(), pdf_id))
             conn.commit()
             continue

        print(f"Baixando: {filename}...", end=" ", flush=True)
        try:
            response = session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                 raise Exception("Recebeu HTML (possível bloqueio Cloudflare)")
            
            if 'application/pdf' not in content_type and 'octet-stream' not in content_type:
                raise Exception(f"Tipo inválido: {content_type}")

            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            cursor.execute("""
                UPDATE pdfs 
                SET status_download = 'sucesso', data_download = ?, erro_download = NULL 
                WHERE id = ?
            """, (datetime.now().isoformat(), pdf_id))
            print("OK")
            consecutive_errors = 0 # Reseta contador de erros
            
        except Exception as e:
            consecutive_errors += 1
            error_msg = str(e)
            print(f"ERRO ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {error_msg}")
            cursor.execute("UPDATE pdfs SET status_download = 'erro', erro_download = ? WHERE id = ?", 
                           (error_msg, pdf_id))
        
        conn.commit()
        time.sleep(SLEEP_TIME)

    conn.close()
    print("Processo finalizado.")

if __name__ == "__main__":
    download_pdfs()
