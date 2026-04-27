# ANEEL RAG — Inteligência Jurídica para o Setor Elétrico

> 🚀 **Disponibilidade:** Este projeto está hospedado e em execução no **Google Cloud Run**, com armazenamento em **Google Cloud Storage (GCS)**, e encontra-se disponível para acesso online.

Este projeto é uma solução avançada de **Retrieval-Augmented Generation (RAG)** projetada para consulta, análise e fundamentação da legislação da Agência Nacional de Energia Elétrica (ANEEL). O sistema utiliza uma arquitetura moderna de agentes baseada em fluxos de trabalho (Workflows) para garantir respostas precisas, auditáveis e tecnicamente embasadas.

## 🏗️ Arquitetura do Sistema e Decisões Técnicas

O sistema foi desenhado para lidar com a complexidade da legislação regulatória, onde o contexto completo é vital para a interpretação jurídica.

### 1. Backend (FastAPI + LlamaIndex v0.14 Workflows)
O coração da aplicação utiliza o novo paradigma de **Workflows do LlamaIndex**, substituindo cadeias rígidas por agentes reativos.
- **Raciocínio Multi-Etapa:** Utilizamos um `FunctionAgent` que orquestra ferramentas dinamicamente. Ele pode, por exemplo, pesquisar ementas, identificar uma norma revogada e buscar automaticamente a norma sucessora.
- **Contratos Fortes (Pydantic):** Todas as ferramentas do agente possuem schemas rigorosos. Isso força o LLM a realizar filtragens precisas por `registro_id`, `situacao` (Vigente/Revogada) e `natureza` do documento (Voto, Nota Técnica, Anexo), reduzindo drasticamente o espaço de alucinação.
- **Gestão de Sessão e Memória:** Implementamos um sistema de persistência em memória que mantém o contexto de workflows por `session_id`. Inclui uma lógica de **garbage collection** que limpa sessões inativas após 1 hora para otimizar recursos.

### 2. Camada de Dados: Estratégia "Parent Retrieval" (Qdrant + GCS)
Uma das decisões mais críticas foi a separação entre a busca vetorial e a entrega de contexto:
- **Busca Semântica (Qdrant Cloud):** Armazena embeddings de fragmentos (chunks) para localização rápida de trechos relevantes.
- **Contexto Integral (GCS):** Ao identificar um trecho relevante, o sistema não entrega apenas o chunk ao LLM. Ele recupera o **Markdown completo** do documento original no Google Cloud Storage. 
- **Justificativa:** No setor elétrico, um artigo isolado pode ser enganoso sem os parágrafos subsequentes ou o preâmbulo. O "Parent Retrieval" via Markdown garante que o LLM tenha a visão total para uma resposta precisa.

### 3. Frontend (Streamlit)
- **Streaming de Estados:** O frontend comunica-se via Event-Stream para mostrar ao usuário o que o agente está fazendo em tempo real ("Pesquisando registros...", "Lendo documento técnico...").
- **Fontes Dinâmicas:** Painel lateral que exibe os metadados das normas citadas e oferece links diretos para os PDFs originais via **URLs assinadas do GCS**, garantindo segurança e acesso imediato.

## 🛠️ Pipeline de Ingestão e Inteligência

O processamento de dados é o que torna o sistema juridicamente "consciente" e é dividido em etapas de alto desempenho:

### 1. Coleta e Downloads (Sincronização)
- **Downloader Inteligente:** O script `download_pdfs.py` gerencia o download de milhares de documentos da ANEEL, utilizando sessões persistentes e controle de taxa para evitar bloqueios, garantindo que a base local e cloud estejam sempre em sincronia com o site oficial.

### 2. Parsing de Alta Performance com Paralelismo
O script `parse_pdfs.py` utiliza uma arquitetura de duas fases para converter PDFs brutos em documentos inteligentes:
- **Fase 1: Detecção de Rasuras (Paralelismo CPU):** Utiliza `multiprocessing` para analisar geometrias de PDFs em paralelo com PyMuPDF. Identifica linhas de cancelamento que indicam revogações, mapeando-as como `~~texto revogado~~`.
- **Fase 2: Conversão Estruturada (Otimização GPU):** Utiliza o motor **Docling** com processamento em lote (`convert_all`) para extrair Markdown de alta qualidade, preservando tabelas e hierarquias, integrado diretamente com aceleração por hardware (CUDA) quando disponível.

### 3. Enriquecimento e Indexação
- **Vetorização:** Geração de embeddings com `text-embedding-3-small` e armazenamento no Qdrant Cloud.
- **Metadados Granulares:** Extração automática de siglas (REN, REH, DSP), IDs de registros e datas, permitindo que o agente realize filtros precisos antes mesmo da busca semântica.

## 🔍 Estratégias de Recuperação (Retrieval)

Para garantir que o sistema não apenas encontre o documento certo, mas forneça a resposta juridicamente correta, implementamos estratégias avançadas:

### 1. Hybrid Retrieval & Metadata Filtering
O sistema utiliza **Contratos Fortes** via Pydantic para guiar o LLM. Antes de buscar, o agente decide se deve aplicar filtros rígidos (ex: "apenas normas vigentes" ou "apenas Resoluções Normativas de 2021"). Isso elimina ruídos e garante que a busca semântica ocorra apenas no subconjunto relevante de dados.

### 2. GCS Full Document Retrieval (Parent Retrieval Customizado)
Diferente de RAGs tradicionais que entregam apenas "pedaços" (chunks) de texto, nosso sistema utiliza um **Retriever Customizado**:
1. **Busca Vetorial:** Localiza os chunks mais similares no Qdrant.
2. **Identificação de Origem:** Extrai o nome do arquivo (`pdf_nome`) dos metadados do chunk.
3. **Recuperação Integral:** O `GCSFullDocumentRetriever` busca o arquivo Markdown completo no Google Cloud Storage.
4. **Contexto Total:** O LLM recebe o documento inteiro, permitindo-lhe entender a hierarquia de artigos, incisos e a fundamentação completa, evitando conclusões baseadas em trechos fora de contexto.

### 3. Detecção Ativa de Revogações
Ao ler o Markdown integral recuperado do GCS, o LLM identifica os marcadores `~~strikethrough~~` gerados na ingestão. Isso permite que o agente informe ao usuário: *"O Artigo X foi localizado, porém encontra-se riscado no documento oficial, indicando sua revogação por uma norma posterior."*

## 📁 Estrutura de Pastas

```text
├── backend/
│   ├── agent/            # Lógica do Agente, Workflows e Tools Pydantic
│   ├── data/             # Base de metadados SQLite e cache local
│   ├── scripts/          # Ingestão, Parsing com detecção de rasuras e Indexação
│   ├── services/         # Clientes para Qdrant Cloud e Google Cloud Storage
│   ├── main.py           # API FastAPI com endpoints de Streaming e Gestão de Sessão
│   └── models.py         # Contratos de dados e Schemas do Agente
├── frontend/
│   └── app.py            # Interface Streamlit com gerenciamento de estado
└── README.md             # Documentação do projeto
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

### Execução via Docker (Recomendado)
A forma mais rápida de iniciar o sistema é utilizando as imagens pré-construídas no Docker Hub:

1. Certifique-se de ter o Docker e Docker Compose instalados.
2. Configure seu arquivo `.env` com as credenciais necessárias.
3. Execute o comando:
   ```bash
   docker-compose up -d
   ```
4. Acesse o Frontend em `http://localhost:8501`.

## ☁️ Deploy
O projeto é implantado no **Google Cloud Run**. O backend e o frontend rodam como serviços independentes, escalando horizontalmente conforme a demanda e consumindo dados de forma centralizada no Qdrant e GCS.
