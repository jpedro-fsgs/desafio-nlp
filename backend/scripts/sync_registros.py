import sqlite3
import json
import re
from pathlib import Path
from tqdm import tqdm

# Configurações de Caminhos
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "aneel_legislacao2.db"
OUTPUT_REGISTROS_DIR = BASE_DIR / "data" / "parsed_docs" / "registros"

def normalizar_data_iso(data_str: str) -> str:
    if not data_str:
        return ""
    # Tenta extrair DD/MM/YYYY e converter para YYYY-MM-DD
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(data_str))
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return str(data_str)

def sincronizar_registros_locais():
    """Busca registros já indexados no banco e salva o JSON localmente."""
    
    # Garante que a pasta existe
    OUTPUT_REGISTROS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Busca apenas quem já está no Qdrant (indexado_qdrant)
    print(f"[*] Lendo registros do banco: {DB_PATH}")
    cursor.execute("""
        SELECT id, titulo, ementa, situacao, publicacao 
        FROM registros 
        WHERE status_ingestao = 'indexado_qdrant'
    """)
    
    rows = cursor.fetchall()
    if not rows:
        print("[!] Nenhum registro com status 'indexado_qdrant' foi encontrado.")
        return

    print(f"[*] Sincronizando {len(rows)} registros para {OUTPUT_REGISTROS_DIR}...")
    
    for row in tqdm(rows, desc="Salvando JSONs"):
        reg_id, titulo, ementa, situacao, data_raw = row
        
        # Estrutura EXATA do payload enviado ao Qdrant
        payload = {
            "registro_id": reg_id,
            "titulo":      titulo,
            "ementa":      ementa,
            "situacao":    situacao,
            "data_iso":    normalizar_data_iso(data_raw),
        }
        
        file_path = OUTPUT_REGISTROS_DIR / f"registro_{reg_id}.json"
        
        # Salva o JSON formatado
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    conn.close()
    print(f"\n[✓] Sincronização concluída. {len(rows)} arquivos salvos.")

if __name__ == "__main__":
    sincronizar_registros_locais()
