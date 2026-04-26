# Estágio de Build
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copia manifestos do workspace
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/
COPY frontend/pyproject.toml ./frontend/

# Instala dependências do frontend
RUN uv sync --package desafio-rag-frontend --frozen --no-cache --no-dev

# Estágio Final (Runtime)
FROM python:3.13-slim

WORKDIR /app

# Copia o ambiente virtual
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copia o código do frontend
COPY frontend/ ./frontend/

# Configurações do Streamlit (PORT será injetada pelo Cloud Run)
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8501

WORKDIR /app
CMD ["sh", "-c", "streamlit run frontend/app.py --server.port=${PORT:-8501} --client.toolbarMode=\"minimal\""]
