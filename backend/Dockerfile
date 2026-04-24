# Estágio de Build
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copia arquivos do workspace e do backend para resolver dependências
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/

# Instala as dependências (ambiente virtual único do workspace)
RUN uv sync --frozen --no-cache --no-dev

# Estágio Final (Runtime)
FROM python:3.13-slim

WORKDIR /app

# Copia o ambiente virtual
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copia o código do backend
COPY backend/ ./backend/

# O CMD deve rodar a partir de dentro da pasta backend para manter caminhos relativos consistentes
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
