# Estágio de Build
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copia os arquivos de configuração do workspace e do frontend
COPY pyproject.toml uv.lock ./
COPY frontend/pyproject.toml ./frontend/

# Instala as dependências (incluindo o workspace para resolver corretamente)
RUN uv sync --frozen --no-cache --no-dev

# Estágio Final (Runtime)
FROM python:3.13-slim

WORKDIR /app

# Copia apenas o ambiente virtual do estágio de build
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copia apenas o código do frontend
COPY frontend/ ./frontend/

# Variáveis de ambiente padrão para o Streamlit
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8501

# Comando para iniciar o Streamlit
CMD ["streamlit", "run", "frontend/app.py"]
