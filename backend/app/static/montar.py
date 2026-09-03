"""Monta o index.html a partir das partes. Rode após editar qualquer _*.

    python3 montar.py

Os quatro arquivos JS são CONCATENADOS dentro de um único <script>, então
compartilham um escopo só. Declarar o mesmo nome em dois deles é SyntaxError,
e SyntaxError não quebra uma função: mata a página inteira, em silêncio, com
tela branca. Já aconteceu (`conta`, utilitário em _telas.js, redeclarado como
objeto de API em _app.js), e o navegador escondeu o estrago por estar servindo
uma versão em cache. Por isso a checagem abaixo roda ANTES de gravar.
"""
import json
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).parent
PARTES_JS = ("_helpers.js", "_app.js", "_telas.js", "_boot.js")

# Declaração no início da linha = topo do escopo compartilhado. Nomes indentados
# são locais de função e não colidem.
DECLARACAO = re.compile(r"^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", re.M)


def ler(nome: str) -> str:
    return (BASE / nome).read_text(encoding="utf-8")


def conferir_colisoes(partes: dict[str, str]) -> list[str]:
    """Nomes declarados no topo de mais de um arquivo."""
    onde: dict[str, list[str]] = {}
    for arquivo, texto in partes.items():
        for nome in DECLARACAO.findall(texto):
            onde.setdefault(nome, []).append(arquivo)
    return [f"  '{nome}' declarado em {' e '.join(arqs)}"
            for nome, arqs in sorted(onde.items()) if len(arqs) > 1]


def main() -> None:
    partes = {nome: ler(nome) for nome in PARTES_JS}

    if colisoes := conferir_colisoes(partes):
        print("COLISÃO DE NOMES — o painel não foi montado.\n", file=sys.stderr)
        print("\n".join(colisoes), file=sys.stderr)
        print("\nOs arquivos JS dividem um escopo só. Renomeie um dos dois — por "
              "convenção, quem chegou depois cede o nome.", file=sys.stderr)
        raise SystemExit(1)

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
{partes['_helpers.js']}
{partes['_app.js']}
{partes['_telas.js']}
{partes['_boot.js']}
</script>
</body>
</html>
"""
    (BASE / "index.html").write_text(html, encoding="utf-8")
    print(f"index.html: {len(html)//1024} KB")


if __name__ == "__main__":
    main()
