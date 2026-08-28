# Sistema Jurídico Domingues — versão de portfólio

Versão pública, leve e sanitizada de um sistema web criado para apoiar a rotina administrativa da Domingues Advogados. O projeto demonstra autenticação, níveis de acesso, painel com indicadores, cadastro de clientes e agenda jurídica.

> Todos os nomes, compromissos e informações iniciais são fictícios. Esta edição não contém banco de produção, documentos jurídicos, credenciais, integrações externas ou dados de clientes reais. A identidade Domingues é utilizada com autorização da empresa.

## Funcionalidades

- Login e criação segura do primeiro administrador
- Perfis de administrador e advogado
- Painel com indicadores e próximos compromissos
- Cadastro, pesquisa, edição e arquivamento de clientes
- Agenda com vínculo entre compromissos e clientes
- Cadastro, ativação e desativação de usuários
- Redefinição de senha com encerramento de sessões anteriores
- Proteção CSRF, hash de senhas, limite de tentativas de login e cabeçalhos de segurança
- Banco SQLite criado automaticamente fora do controle de versão
- Dados fictícios gerados automaticamente para demonstração

## Tecnologias

- Python 3.11+
- Flask 3
- SQLite
- HTML, CSS e JavaScript
- Pytest

## Como executar no Windows

No PowerShell, dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Abra `http://127.0.0.1:5000` no navegador. No primeiro acesso, o próprio sistema solicitará a criação do administrador. A senha deve ter pelo menos 12 caracteres.

## Como executar no Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## Testes

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

## Estrutura resumida

```text
app.py                 aplicação, rotas e banco SQLite
templates/             telas Jinja/HTML
static/                identidade visual e JavaScript
tests/                  testes automatizados
instance/               banco e chave locais (ignorada pelo Git)
```

## Decisões da versão pública

A versão interna possui módulos e integrações que não fazem parte deste repositório. Para reduzir riscos e facilitar a avaliação do código, esta demonstração mantém somente o núcleo escolhido para o portfólio: painel, clientes, agenda, login e usuários.

Não publique arquivos da pasta `instance`, arquivos `.env`, cópias de segurança, documentos ou capturas de tela contendo informações reais.

## Autoria

Desenvolvido por **Lucas Gabriel Domingues de Souza**, estudante de Análise e Desenvolvimento de Sistemas, como projeto aplicado à rotina de um escritório jurídico, com apoio de ferramentas de inteligência artificial durante o desenvolvimento e a revisão.

Este repositório é apresentado para fins de estudo e portfólio. Nenhuma licença de reutilização é concedida neste momento.
