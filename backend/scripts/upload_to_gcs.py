import os
import threading
import signal
import sys
from google.cloud import storage
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from config import GCS_BUCKET_NAME, DOWNLOADS_DIR

# --- CONFIGURAÇÃO ---
MAX_WORKERS = 15
MAX_CONSECUTIVE_ERRORS = 20

# Variáveis globais para controle
stats_lock = threading.Lock()
stats = {
    "uploaded": 0,
    "skipped": 0,
    "errors": 0,
    "consecutive_errors": 0
}
shutdown_event = threading.Event()

def upload_single_file(bucket_name, filename):
    """Função para subir um único arquivo com check de interrupção."""
    global stats
    if shutdown_event.is_set():
        return "cancelled"

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        local_path = os.path.join(DOWNLOADS_DIR, filename)
        blob = bucket.blob(filename)

        if blob.exists():
            with stats_lock:
                stats["skipped"] += 1
                stats["consecutive_errors"] = 0
            return "skipped"
        
        if shutdown_event.is_set(): return "cancelled"
        
        blob.upload_from_filename(local_path)
        
        with stats_lock:
            stats["uploaded"] += 1
            stats["consecutive_errors"] = 0
        return "uploaded"
        
    except Exception as e:
        with stats_lock:
            stats["errors"] += 1
            stats["consecutive_errors"] += 1
        return f"error: {str(e)}"

def upload_pdfs_to_gcs_parallel():
    """Sobe os PDFs com tratamento gracioso de interrupção (Ctrl+C)."""
    if not os.path.exists(DOWNLOADS_DIR):
        print(f"Erro: Diretório {DOWNLOADS_DIR} não encontrado.")
        return

    files = [f for f in os.listdir(DOWNLOADS_DIR) if f.lower().endswith('.pdf')]
    total_files = len(files)
    
    if total_files == 0:
        print("Nenhum PDF encontrado para upload.")
        return

    print(f"Iniciando upload de {total_files} arquivos (Pressione Ctrl+C para parar com segurança)...")

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(upload_single_file, GCS_BUCKET_NAME, f): f for f in files}
            
            with tqdm(total=total_files, desc="Upload para GCS", unit="file") as pbar:
                try:
                    for future in as_completed(futures):
                        if shutdown_event.is_set():
                            break
                            
                        # Check de segurança por erros seguidos
                        with stats_lock:
                            if stats["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
                                print(f"\n\n[!] ERROS SEGUIDOS: {stats['consecutive_errors']}. Parando...")
                                shutdown_event.set()
                                break
                        
                        result = future.result()
                        pbar.update(1)
                        
                        with stats_lock:
                            pbar.set_postfix({
                                "OK": stats["uploaded"],
                                "Pulo": stats["skipped"],
                                "Erro": stats["errors"]
                            })
                except KeyboardInterrupt:
                    print("\n\n[!] INTERRUPÇÃO DETECTADA: Finalizando tarefas em andamento e saindo...")
                    shutdown_event.set()
                    # Cancela futuros pendentes
                    executor.shutdown(wait=False, cancel_futures=True)

    except Exception as e:
        print(f"\nErro inesperado no executor: {e}")

    # Resumo sempre é exibido, mesmo após interrupção
    print(f"\n\n--- Resumo Final (Status: {'Interrompido' if shutdown_event.is_set() else 'Concluído'}) ---")
    print(f"Total processado: {stats['uploaded'] + stats['skipped'] + stats['errors']}/{total_files}")
    print(f"Novos subidos: {stats['uploaded']}")
    print(f"Já existentes: {stats['skipped']}")
    print(f"Falhas: {stats['errors']}")

if __name__ == "__main__":
    upload_pdfs_to_gcs_parallel()
