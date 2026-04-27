# Estágio de Build
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/
COPY frontend/pyproject.toml ./frontend/

# 1. Só dependências (camada cacheável)
RUN uv sync --package desafio-rag-backend --frozen --no-cache --no-dev --no-install-project

# 2. Copia o fonte
COPY backend/ ./backend/

# 3. Instala o projeto em si
RUN uv sync --package desafio-rag-backend --frozen --no-cache --no-dev

# Estágio Final (Runtime)
FROM python:3.13-slim

WORKDIR /app

# Copia o ambiente virtual
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copia o código fonte do backend
COPY backend/ ./backend/

# Ajusta diretório de trabalho para execução
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
