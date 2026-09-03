"""Monta o index.html a partir das partes. Rode após editar qualquer _*.

    python3 montar.py
"""
import json
import pathlib

BASE = pathlib.Path(__file__).parent
def ler(nome: str) -> str:
    return (BASE / nome).read_text(encoding="utf-8")

html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel Jurídico — Pradópolis</title>
{ler('_estilo.html')}
</head>
<body>
<script>
const SHELL = {json.dumps(ler('_shell.html'), ensure_ascii=False)};
{ler('_helpers.js')}
{ler('_app.js')}
{ler('_telas.js')}
{ler('_boot.js')}
</script>
</body>
</html>
"""
(BASE / "index.html").write_text(html, encoding="utf-8")
print(f"index.html: {len(html)//1024} KB")
