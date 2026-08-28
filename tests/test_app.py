from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from app import create_app, query_one


ADMIN_PASSWORD = "SenhaDeTeste@2026"


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "SECRET_KEY": "chave-de-testes-com-tamanho-suficiente",
            "SEED_DEMO": True,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def create_admin(client):
    response = client.post(
        "/primeiro-acesso",
        data={
            "display_name": "Administrador de Teste",
            "username": "admin_teste",
            "password": ADMIN_PASSWORD,
            "confirmation": ADMIN_PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def login_admin(client):
    response = client.post(
        "/entrar",
        data={"username": "admin_teste", "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.headers["Location"].endswith("/")


def test_first_access_login_and_dashboard(client):
    assert client.get("/").headers["Location"].endswith("/primeiro-acesso")
    create_admin(client)
    login_admin(client)

    response = client.get("/")
    assert response.status_code == 200
    assert "Clientes ativos" in response.get_data(as_text=True)
    assert response.headers["X-Frame-Options"] == "DENY"


def test_client_and_agenda_flow(app, client):
    create_admin(client)
    login_admin(client)

    response = client.post(
        "/clientes",
        data={
            "full_name": "Cliente Automatizado — demonstração",
            "contract_signed_on": "2026-08-01",
            "procedural_stage": "Aguardando audiência",
        },
        follow_redirects=True,
    )
    assert "Cliente cadastrado" in response.get_data(as_text=True)
    client_id = query_one(
        app.config["DATABASE"],
        "SELECT id FROM clients WHERE full_name LIKE 'Cliente Automatizado%'",
    )["id"]

    start_at = (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes")
    response = client.post(
        "/agenda",
        data={
            "title": "Audiência automatizada — demonstração",
            "event_type": "audiencia",
            "start_at": start_at,
            "end_at": "",
            "client_id": str(client_id),
            "location": "Fórum de teste",
            "description": "Registro fictício.",
        },
        follow_redirects=True,
    )
    assert "Compromisso salvo" in response.get_data(as_text=True)
    assert "Audiência automatizada" in response.get_data(as_text=True)

    clients_page = client.get("/clientes").get_data(as_text=True)
    assert "Cliente Automatizado" in clients_page
    assert "Nenhuma agendada" not in clients_page.split("Cliente Automatizado", 1)[1].split("</article>", 1)[0]


def test_admin_can_create_user_and_regular_user_cannot_administer(client):
    create_admin(client)
    login_admin(client)
    user_password = "SenhaAdvogado@2026"

    response = client.post(
        "/usuarios",
        data={
            "display_name": "Usuário de Teste",
            "username": "usuario_teste",
            "role": "advogado",
            "password": user_password,
            "confirmation": user_password,
        },
        follow_redirects=True,
    )
    assert "Usuário cadastrado" in response.get_data(as_text=True)

    client.post("/sair")
    client.post(
        "/entrar",
        data={"username": "usuario_teste", "password": user_password},
    )
    assert client.get("/usuarios").status_code == 403


def test_csrf_is_required_outside_testing(tmp_path):
    app = create_app(
        {
            "TESTING": False,
            "DATABASE": str(tmp_path / "csrf.sqlite3"),
            "SECRET_KEY": "chave-csrf-com-tamanho-suficiente",
            "SEED_DEMO": False,
        }
    )
    client = app.test_client()

    response = client.get("/primeiro-acesso")
    html = response.get_data(as_text=True)
    assert re.search(r'name="csrf_token" value="[^"]+"', html)

    response = client.post(
        "/primeiro-acesso",
        data={
            "display_name": "Admin",
            "username": "admin",
            "password": ADMIN_PASSWORD,
            "confirmation": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 400
