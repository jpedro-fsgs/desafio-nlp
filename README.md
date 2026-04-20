# Desafio RAG - Legislação ANEEL

Este repositório contém uma solução completa de **Retrieval-Augmented Generation (RAG)** projetada para consulta e análise da legislação da Agência Nacional de Energia Elétrica (ANEEL). O sistema processa milhares de documentos normativos, organiza metadados estruturados e permite buscas semânticas de alta precisão.

## Objetivo
O objetivo principal deste projeto é transformar o acervo de atos administrativos da ANEEL (Resoluções, Despachos, Portarias) em uma base de conhecimento inteligente, capaz de responder perguntas complexas com base no texto integral das normas originais.

## Arquitetura do Sistema

O projeto utiliza uma estratégia de **Recuperação em Duas Etapas (Small-to-Big Retrieval)** para otimizar o custo e a precisão:

1.  **Camada Semântica (Ementas)**: O sistema indexa as ementas e títulos dos documentos no **Qdrant**. Devido à alta densidade semântica desses resumos, a busca inicial é extremamente rápida e assertiva.
2.  **Camada de Contexto (PDF Integral)**: Após identificar os documentos mais relevantes, o sistema recupera o caminho dos arquivos originais em um banco **SQLite** e extrai o texto integral dos PDFs no disco para fornecer o contexto completo ao modelo de linguagem (LLM).

## Principais Componentes

*   **API FastAPI**: Interface RESTful modularizada com endpoints para consulta semântica e geração de respostas fundamentadas.
*   **Banco de Vetores Qdrant**: Motor de busca semântica de alta performance para armazenamento de embeddings e metadados.
*   **Banco de Dados SQLite**: Armazenamento estruturado de metadados normalizados, status de download e vínculos entre registros e arquivos físicos.
*   **Orquestração LlamaIndex**: Framework utilizado para gerenciar o fluxo de dados entre o banco vetorial, o sistema de arquivos e o LLM.

## Tecnologias Utilizadas

*   **Linguagem**: Python 3.13+
*   **IA/LLM**: OpenAI (GPT-4o-mini e text-embedding-3-small)
*   **Banco de Vetores**: Qdrant
*   **Banco SQL**: SQLite
*   **Framework Web**: FastAPI
*   **Gerenciamento de Dependências**: uv
*   **Containerização**: Docker e Docker Compose

## Estrutura de Dados e Normalização
O projeto conta com um pipeline de dados que realiza a limpeza e normalização de milhares de registros, convertendo variações ruidosas em categorias consistentes (ex: Texto Integral, Voto, Nota Técnica) e removendo resquícios de interface das ementas, garantindo metadados de alta qualidade para o RAG.
