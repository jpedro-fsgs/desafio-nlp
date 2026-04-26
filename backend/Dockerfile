# Estágio de Build
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copia manifestos do workspace para resolução de dependências
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/
COPY frontend/pyproject.toml ./frontend/

# Instala dependências do backend (focado no pacote específico)
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
