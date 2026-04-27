FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/
COPY frontend/pyproject.toml ./frontend/

# 1. Só dependências (camada cacheável)
RUN uv sync --package desafio-rag-frontend --frozen --no-cache --no-dev --no-install-project

# 2. Copia o fonte
COPY frontend/ ./frontend/

# 3. Instala o projeto
RUN uv sync --package desafio-rag-frontend --frozen --no-cache --no-dev

FROM python:3.13-slim
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

COPY frontend/ ./frontend/

EXPOSE 8501
CMD ["sh", "-c", "streamlit run frontend/app.py --server.port=${PORT:-8501} --client.toolbarMode=\"minimal\""]