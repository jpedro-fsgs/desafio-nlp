import sqlite3
import requests
import os
import time
from datetime import datetime

# --- CONFIGURAÇÃO ---
DB_NAME = "aneel_legislacao.db"
DOWNLOAD_DIR = "downloads_extra"  # Pasta separada para não misturar com os PDFs
SLEEP_TIME = 1.0 
MAX_CONSECUTIVE_ERRORS = 5 

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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

def download_others(limit=None):
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Seleciona apenas os que NÃO foram baixados com sucesso
    query = "SELECT id, url, arquivo FROM pdfs WHERE status_download != 'sucesso'"
    if limit:
        query += f" LIMIT {limit}"
        
    cursor.execute(query)
    pending_files = cursor.fetchall()

    if not pending_files:
        print("Nenhum arquivo pendente.")
        conn.close()
        return

    print(f"Iniciando busca por arquivos NÃO-PDF em {len(pending_files)} registros.")

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
    downloaded_count = 0

    for file_id, url, filename in pending_files:
        url = url.strip()
        if filename:
            filename = filename.strip()
        
        if not filename:
            filename = url.split("/")[-1].split("?")[0]

        # SE FOR PDF, PULA (Este script é para os outros formatos)
        if filename.lower().endswith(".pdf"):
            continue

        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"\n[!] PARANDO: {consecutive_errors} erros consecutivos.")
            break

        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)
            
        local_path = os.path.join(DOWNLOAD_DIR, filename)
        
        # Pula se já existe
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
             cursor.execute("UPDATE pdfs SET status_download = 'sucesso', data_download = ? WHERE id = ?", 
                           (datetime.now().isoformat(), file_id))
             conn.commit()
             continue

        print(f"Baixando Extra: {filename}...", end=" ", flush=True)
        try:
            response = session.get(url, timeout=30, allow_redirects=True)
            
            # Verifica bloqueio explícito
            if response.status_code == 403:
                raise Exception("Erro 403: Bloqueio Cloudflare (Acesso Proibido)")
                
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            
            # Se for HTML, verifica se é conteúdo real ou desafio da Cloudflare
            if 'text/html' in content_type:
                 content_sample = response.content.lower()
                 if b"cloudflare" in content_sample or b"ray id" in content_sample or b"captcha" in content_sample:
                      raise Exception("Bloqueio Cloudflare detectado no conteúdo HTML")
                 
                 # Se for uma página muito pequena (menos de 1KB), pode ser um erro não detectado
                 if len(response.content) < 1000 and b"error" in content_sample:
                      raise Exception(f"Página de erro detectada (tamanho: {len(response.content)} bytes)")

            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            cursor.execute("""
                UPDATE pdfs 
                SET status_download = 'sucesso', data_download = ?, erro_download = NULL 
                WHERE id = ?
            """, (datetime.now().isoformat(), file_id))
            print("OK")
            consecutive_errors = 0 
            downloaded_count += 1
            
        except Exception as e:
            consecutive_errors += 1
            error_msg = str(e)
            print(f"ERRO ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {error_msg}")
            cursor.execute("UPDATE pdfs SET status_download = 'erro', erro_download = ? WHERE id = ?", 
                           (error_msg, file_id))
        
        conn.commit()
        time.sleep(SLEEP_TIME)

    conn.close()
    print(f"Processo finalizado. {downloaded_count} arquivos extras baixados.")

if __name__ == "__main__":
    download_others()
