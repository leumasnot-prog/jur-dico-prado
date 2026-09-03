FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# O contexto de build é a RAIZ do repositório (ver render.yaml: dockerContext),
# não backend/. A estrutura é espelhada aqui em vez de achatada, porque o
# pyproject.toml do backend resolve o MCP com um path RELATIVO
# ([tool.uv.sources] mcp-juridico-brasil = {path = "..", editable = true}):
# "backend/pyproject.toml" instalado a partir de "/src/backend" precisa achar
# o MCP em "/src", exatamente como acha ".." localmente.
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src

WORKDIR /src/backend
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache .

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

EXPOSE 8000
# Migra e sobe. Falha na migração derruba o container, o que é o certo:
# subir com schema desatualizado é pior que não subir.
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
