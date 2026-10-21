from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime, timedelta

import pytest

import app as app_module

from app import create_app, execute, query_one


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


def add_event(app, title, start_at, event_type="reuniao", client_id=None, status="active"):
    return execute(
        app.config["DATABASE"],
        """
        INSERT INTO events (title, event_type, start_at, client_id, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, event_type, start_at, client_id, status),
    )


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


def test_dashboard_shows_overdue_events(app, client):
    create_admin(client)
    login_admin(client)
    past = (datetime.now() - timedelta(days=2)).isoformat(timespec="minutes")
    add_event(app, "Prazo vencido — demonstração", past, event_type="prazo")
    add_event(app, "Prazo já concluído — demonstração", past, status="completed")

    html = client.get("/").get_data(as_text=True)
    assert 'class="overdue-panel"' in html
    overdue = html.split('class="overdue-panel"', 1)[1].split("</section>", 1)[0]
    assert "Prazo vencido" in overdue
    assert "Prazo já concluído" not in overdue
    assert html.index("overdue-panel") < html.index("stats-grid")


def test_dashboard_hides_overdue_block_when_nothing_is_late(client):
    create_admin(client)
    login_admin(client)
    assert "overdue-panel" not in client.get("/").get_data(as_text=True)


def test_next_hearing_uses_local_time_not_utc(app, client, monkeypatch):
    # Simula o servidor no Brasil (UTC-3): CURRENT_TIMESTAMP do SQLite fica 3h à frente.
    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    time.tzset()
    try:
        create_admin(client)
        login_admin(client)
        client_id = execute(
            app.config["DATABASE"],
            "INSERT INTO clients (full_name, contract_signed_on) VALUES (?, ?)",
            ("Cliente Fuso — demonstração", "2026-01-10"),
        )
        soon = (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes")
        add_event(app, "Audiência em 1h — demonstração", soon, "audiencia", client_id)

        html = client.get("/clientes").get_data(as_text=True)
        card = html.split("Cliente Fuso", 1)[1].split("</article>", 1)[0]
        assert "Nenhuma agendada" not in card
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_error_pages_use_portuguese_messages(client):
    create_admin(client)
    login_admin(client)
    response = client.get("/pagina-que-nao-existe")
    assert response.status_code == 404
    assert "A página solicitada não foi encontrada." in response.get_data(as_text=True)


def test_error_pages_keep_message_given_to_abort(client):
    create_admin(client)
    login_admin(client)
    response = client.post("/clientes/1/arquivar", data={"confirm_id": "999"})
    assert response.status_code == 400
    assert "O arquivamento não foi confirmado." in response.get_data(as_text=True)


def test_agenda_shows_event_type_with_accents(app, client):
    create_admin(client)
    login_admin(client)
    future = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
    add_event(app, "Encontro — demonstração", future, "reuniao")
    add_event(app, "Sessão — demonstração", future, "audiencia")

    html = client.get("/agenda").get_data(as_text=True)
    timeline = html.split('class="timeline"', 1)[1]
    assert "· Reunião" in timeline
    assert "· Audiência" in timeline
    assert "Reuniao" not in timeline and "Audiencia" not in timeline


def test_agenda_stores_normalized_dates(app, client):
    create_admin(client)
    login_admin(client)
    client.post(
        "/agenda",
        data={
            "title": "Datas normalizadas — demonstração",
            "event_type": "reuniao",
            "start_at": "2030-05-10 09:30:45",
            "end_at": "2030-05-10T10:15:59",
        },
    )
    row = query_one(
        app.config["DATABASE"],
        "SELECT start_at, end_at FROM events WHERE title LIKE 'Datas normalizadas%'",
    )
    assert row["start_at"] == "2030-05-10T09:30"
    assert row["end_at"] == "2030-05-10T10:15"


def test_db_helpers_close_their_connections(tmp_path, monkeypatch):
    opened = []
    real_connect = app_module.connect

    def tracking_connect(database):
        connection = real_connect(database)
        opened.append(connection)
        return connection

    monkeypatch.setattr(app_module, "connect", tracking_connect)
    database = tmp_path / "conexoes.sqlite3"
    app_module.init_db(database)
    app_module.seed_demo_data(database)
    app_module.execute(database, "INSERT INTO login_attempts (username, remote_addr) VALUES ('x', 'y')")
    app_module.query_one(database, "SELECT 1")
    app_module.query_all(database, "SELECT 1")

    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
