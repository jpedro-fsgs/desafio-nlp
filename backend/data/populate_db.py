import sqlite3
import json
import os
import glob
from data.model_dados import Model, RegistroDiario, Registros, Pdf

DB_NAME = "aneel_legislacao.db"
DATA_DIR = "dados_grupo_estudos"

def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_referencia TEXT,
            numeracaoItem TEXT,
            titulo TEXT,
            autor TEXT,
            material TEXT,
            esfera TEXT,
            situacao TEXT,
            assinatura TEXT,
            publicacao TEXT,
            assunto TEXT,
            ementa TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pdfs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registro_id INTEGER,
            tipo TEXT,
            url TEXT,
            arquivo TEXT,
            baixado_original BOOLEAN,
            status_download TEXT DEFAULT 'pendente',
            data_download TIMESTAMP,
            erro_download TEXT,
            FOREIGN KEY (registro_id) REFERENCES registros(id)
        )
    """)

def populate_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    create_tables(cursor)
    
    json_files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    
    for json_file in json_files:
        print(f"Processando {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Parse using Pydantic for validation
        model_instance = Model.model_validate(data)
        
        for date_ref, diario in model_instance.root.items():
            for reg in diario.registros:
                cursor.execute("""
                    INSERT INTO registros (
                        data_referencia, numeracaoItem, titulo, autor, material,
                        esfera, situacao, assinatura, publicacao, assunto, ementa
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_ref, reg.numeracaoItem, reg.titulo, reg.autor, reg.material,
                    reg.esfera, reg.situacao, reg.assinatura, reg.publicacao, reg.assunto, reg.ementa
                ))
                registro_id = cursor.lastrowid
                
                for pdf in reg.pdfs:
                    cursor.execute("""
                        INSERT INTO pdfs (
                            registro_id, tipo, url, arquivo, baixado_original
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        registro_id, pdf.tipo, pdf.url, pdf.arquivo, pdf.baixado
                    ))
        conn.commit()
    
    conn.close()
    print("População do banco de dados concluída.")

if __name__ == "__main__":
    populate_db()
