#!/bin/bash
# build.sh

echo "Building Backend (jpedrofsgs/aneel-rag-backend)..."
docker build --no-cache -t jpedrofsgs/aneel-rag-backend:latest -f backend/Dockerfile .

echo "Building Frontend (jpedrofsgs/aneel-rag-frontend)..."
docker build --no-cache -t jpedrofsgs/aneel-rag-frontend:latest -f frontend/Dockerfile .

echo "Builds concluídos com sucesso!"
echo "Para subir o ambiente: docker compose up"
