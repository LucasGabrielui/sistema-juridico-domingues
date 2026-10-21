# Regras do projeto — Sistema Jurídico Domingues

Flask + SQLite (`app.py`, `templates/`, `static/`, `tests/`).

## Forma de trabalho
- Trabalhar em FASES. Ao fim de cada fase: rodar `pytest -q`, fazer commit,
  mostrar um resumo em português simples do que mudou e por quê, e PARAR
  esperando o "pode seguir".
- Todo o trabalho fica na branch `melhorias`.
- Uma mudança por commit, com mensagem clara em português.
- Toda correção ganha um teste que falharia antes e passa depois.
- Não mudar comportamento que não foi pedido.
- Nunca usar dados reais de clientes (só dados fictícios, marcados como "demonstração").
- Explicar as mudanças de forma didática: o autor é estudante de ADS.

## Identidade visual
- Menu lateral escuro (azul-marinho) e detalhes dourados.

## Comandos
- Instalar: `python -m pip install -r requirements-dev.txt`
- Testes: `pytest -q`
