# ANEEL RAG — Inteligência Jurídica para o Setor Elétrico

Este projeto é uma solução avançada de **Retrieval-Augmented Generation (RAG)** projetada para consulta, análise e fundamentação da legislação da Agência Nacional de Energia Elétrica (ANEEL). O sistema utiliza uma arquitetura moderna de agentes baseada em fluxos de trabalho (Workflows) para garantir respostas precisas e atualizadas.

## 🏗️ Arquitetura do Sistema

O sistema é dividido em três camadas principais, garantindo escalabilidade e separação de responsabilidades:

### 1. Backend (FastAPI + LlamaIndex v0.14)
O coração da aplicação utiliza o novo paradigma de **Workflows do LlamaIndex**.
- **Agente de Função:** Um `FunctionAgent` orquestra o raciocínio, decidindo quando buscar metadados macro ou mergulhar em detalhes técnicos de PDFs.
- **Contratos Fortes:** Todas as ferramentas do agente possuem schemas Pydantic extensivamente documentados, permitindo filtragem precisa por IDs, situações jurídicas (Vigente/Revogada), siglas e períodos de data.
- **Gestão de Sessão:** Sessões em memória que sobrevivem a recargas de página (F5) através de associação por `user_id` na URL e `session_id` interno. Possui limpeza automática de sessões inativas (1 hora).

### 2. Camada de Dados e Recuperação (Hybrid Search + Parent Retrieval)
- **Qdrant Cloud:** Banco de vetores que armazena embeddings de alta densidade (`text-embedding-3-small`) para busca semântica em dois níveis: Registros (Ementas) e Documentos Técnicos (Chunks de PDFs).
- **Google Cloud Storage (GCS):** Atua como o repositório de verdade para documentos íntegros.
- **Estratégia Parent Retrieval:** O sistema identifica o trecho relevante no Qdrant, mas recupera o **Markdown completo** no GCS para fornecer o contexto total ao LLM, eliminando o problema de "chunks sem contexto".

### 3. Frontend (Streamlit)
- Interface profissional e minimalista com painel lateral de fontes dinâmico.
- Renderização inteligente: Registros exibem ementas expansíveis, enquanto documentos técnicos (PDFs) oferecem links diretos de acesso via URLs assinadas do GCS.

## 🛠️ Pipeline de Ingestão e Inteligência

O processamento de dados (`backend/scripts/indexar_metadados.py`) conta com:
- **PyMuPDFParser:** Conversor especializado que detecta rasuras geométricas no PDF e as marca como `~~texto~~` no Markdown, permitindo que o agente identifique visualmente trechos revogados.
- **Extração de Metadados:** Mapeamento automático de siglas (REN, REH, DSP) e naturezas técnicas.
- **Upload Sincronizado:** Cada documento processado é automaticamente salvo em disco e sincronizado com o Bucket do GCS.

## 📁 Estrutura de Pastas

```text
├── backend/
│   ├── agent/            # Lógica do Agente e Ferramentas (Tools)
│   ├── data/             # Base de dados SQLite local e armazenamento temporário
│   ├── scripts/          # Scripts utilitários de Ingestão, Download e Parsing
│   ├── services/         # Integrações com Qdrant Cloud e GCS
│   ├── main.py           # API FastAPI
│   └── models.py         # Contratos de dados Pydantic
├── frontend/
│   └── app.py            # Interface Streamlit
└── cloudbuild.yaml       # Configuração de CI/CD para Google Cloud
```

## 🚀 Como Executar

### Pré-requisitos
- Python 3.13+
- Gerenciador de pacotes `uv` (recomendado)
- Chaves de API: OpenAI, Qdrant Cloud e Google Cloud Credentials.

### Instalação
1. Clone o repositório.
2. Instale as dependências:
   ```bash
   uv sync
   ```
3. Configure o arquivo `.env` baseado no `.env.example`.

### Execução
1. Inicie o Backend:
   ```bash
   cd backend
   python main.py
   ```
2. Em outro terminal, inicie o Frontend:
   ```bash
   cd frontend
   streamlit run app.py
   ```

## ☁️ Deploy
O projeto está preparado para deploy no **Google Cloud Run** via **Cloud Build**. O build é disparado automaticamente a partir da raiz, configurando os serviços de Backend e Frontend como containers independentes que se comunicam via rede interna ou pública.
