FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# A lib de domínio (MCP) vem do diretório pai — copiada antes para aproveitar cache.
COPY ../pyproject.toml ../README.md /mcp/
COPY ../src /mcp/src

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache /mcp && \
    uv pip install --system --no-cache .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
# Migra e sobe. Falha na migração derruba o container, o que é o certo:
# subir com schema desatualizado é pior que não subir.
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
