from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Iterable

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EVENT_TYPES = {"audiencia", "prazo", "reuniao", "televisita", "outro"}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'advogado')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    session_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    contract_signed_on TEXT NOT NULL,
    procedural_stage TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_by_user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('audiencia', 'prazo', 'reuniao', 'televisita', 'outro')
    ),
    start_at TEXT NOT NULL,
    end_at TEXT,
    location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    client_id INTEGER REFERENCES clients(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
    created_by_user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    remote_addr TEXT NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clients_active_name ON clients(active, full_name);
CREATE INDEX IF NOT EXISTS idx_events_status_start ON events(status, start_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON login_attempts(attempted_at);
"""


def connect(database: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def init_db(database: str | Path) -> None:
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as connection:
        connection.executescript(SCHEMA)


def query_one(
    database: str | Path, sql: str, params: Iterable[Any] = ()
) -> sqlite3.Row | None:
    with connect(database) as connection:
        return connection.execute(sql, tuple(params)).fetchone()


def query_all(
    database: str | Path, sql: str, params: Iterable[Any] = ()
) -> list[sqlite3.Row]:
    with connect(database) as connection:
        return connection.execute(sql, tuple(params)).fetchall()


def execute(database: str | Path, sql: str, params: Iterable[Any] = ()) -> int:
    with connect(database) as connection:
        cursor = connection.execute(sql, tuple(params))
        connection.commit()
        return int(cursor.lastrowid)


def secret_key(instance_path: str, configured: str | None = None) -> str:
    if configured and configured != "troque-esta-chave":
        return configured
    path = Path(instance_path) / ".secret_key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip()


def seed_demo_data(database: str | Path) -> None:
    """Inclui apenas registros fictícios para a apresentação do portfólio."""
    if query_one(database, "SELECT COUNT(*) AS total FROM clients")["total"]:
        return

    today = date.today()
    now = datetime.now().replace(second=0, microsecond=0)
    clients = [
        ("Ana Martins — demonstração", (today - timedelta(days=95)).isoformat(), "Fase de conhecimento"),
        ("Bruno Almeida — demonstração", (today - timedelta(days=61)).isoformat(), "Aguardando audiência"),
        ("Empresa Horizonte — demonstração", (today - timedelta(days=34)).isoformat(), "Análise documental"),
    ]
    with connect(database) as connection:
        connection.executemany(
            "INSERT INTO clients (full_name, contract_signed_on, procedural_stage) VALUES (?, ?, ?)",
            clients,
        )
        client_ids = [
            row["id"]
            for row in connection.execute("SELECT id FROM clients ORDER BY id").fetchall()
        ]
        events = [
            (
                "Audiência de conciliação — demonstração",
                "audiencia",
                (now + timedelta(days=3, hours=2)).isoformat(timespec="minutes"),
                None,
                "Fórum Central",
                "Compromisso fictício para apresentação.",
                client_ids[1],
            ),
            (
                "Reunião de alinhamento — demonstração",
                "reuniao",
                (now + timedelta(days=6)).isoformat(timespec="minutes"),
                (now + timedelta(days=6, hours=1)).isoformat(timespec="minutes"),
                "Videoconferência",
                "Compromisso fictício para apresentação.",
                client_ids[2],
            ),
            (
                "Revisão de documentos — demonstração",
                "prazo",
                (now + timedelta(days=10)).isoformat(timespec="minutes"),
                None,
                "Escritório",
                "Compromisso fictício para apresentação.",
                client_ids[0],
            ),
        ]
        connection.executemany(
            """
            INSERT INTO events
                (title, event_type, start_at, end_at, location, description, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            events,
        )
        connection.commit()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_path=str(BASE_DIR / "instance"),
        instance_relative_config=True,
    )
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "portfolio.sqlite3"),
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "troque-esta-chave"),
        CSRF_ENABLED=True,
        SEED_DEMO=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("APP_HTTPS", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
        LOGIN_MAX_ATTEMPTS=5,
        LOGIN_MAX_IP_ATTEMPTS=20,
        LOGIN_WINDOW_MINUTES=15,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config["SECRET_KEY"] = secret_key(
        app.instance_path, app.config.get("SECRET_KEY")
    )
    init_db(app.config["DATABASE"])
    if app.config.get("SEED_DEMO"):
        seed_demo_data(app.config["DATABASE"])

    def current_user_id() -> int | None:
        user = getattr(g, "user", None)
        return int(user["id"]) if user else None

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "user", None) or g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    @app.before_request
    def load_user_and_require_login():
        g.user = None
        user_count = query_one(
            app.config["DATABASE"], "SELECT COUNT(*) AS total FROM users"
        )["total"]

        if user_count == 0 and request.endpoint not in {
            "static",
            "first_access",
            "health",
        }:
            return redirect(url_for("first_access"))

        user_id = session.get("user_id")
        if user_id:
            user = query_one(
                app.config["DATABASE"],
                """
                SELECT id, username, display_name, role, active, session_version
                  FROM users WHERE id=? AND active=1
                """,
                (user_id,),
            )
            if user and int(session.get("session_version", 0)) == int(
                user["session_version"]
            ):
                g.user = user
            else:
                session.clear()

        if request.endpoint not in {
            "static",
            "first_access",
            "login",
            "health",
        } and g.user is None:
            return redirect(url_for("login"))
        return None

    @app.before_request
    def validate_csrf():
        if (
            request.method in SAFE_METHODS
            or app.config.get("TESTING")
            or not app.config.get("CSRF_ENABLED")
        ):
            return None
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("csrf_token", "") or request.headers.get(
            "X-CSRF-Token", ""
        )
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description="Formulário expirado. Atualize a página e tente novamente.")
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if g.get("user"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def template_context():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return {"csrf_token": token, "current_user": getattr(g, "user", None)}

    @app.template_filter("brdate")
    def brdate(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y às %H:%M")
        except ValueError:
            return str(value)

    @app.template_filter("brday")
    def brday(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
        except ValueError:
            return str(value)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def friendly_error(error):
        messages = {
            400: "A solicitação não pôde ser validada.",
            403: "Sua conta não possui permissão para esta ação.",
            404: "A página solicitada não foi encontrada.",
        }
        return (
            render_template(
                "error.html",
                code=error.code,
                message=getattr(error, "description", messages[error.code]),
            ),
            error.code,
        )

    @app.get("/saude")
    def health():
        try:
            result = query_one(app.config["DATABASE"], "PRAGMA quick_check")[0]
            healthy = result == "ok"
        except sqlite3.Error:
            healthy = False
        return jsonify(status="ok" if healthy else "erro", demo=True), 200 if healthy else 503

    @app.route("/primeiro-acesso", methods=["GET", "POST"])
    def first_access():
        if query_one(app.config["DATABASE"], "SELECT COUNT(*) AS total FROM users")["total"]:
            return redirect(url_for("login"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()[:40]
            display_name = request.form.get("display_name", "").strip()[:100]
            password = request.form.get("password", "")
            confirmation = request.form.get("confirmation", "")
            if len(username) < 3 or not username.replace("_", "").isalnum():
                flash("Use ao menos 3 letras ou números no nome de usuário.", "error")
            elif len(display_name) < 3:
                flash("Informe o nome do administrador.", "error")
            elif len(password) < 12:
                flash("A senha precisa ter ao menos 12 caracteres.", "error")
            elif password != confirmation:
                flash("As senhas não conferem.", "error")
            else:
                execute(
                    app.config["DATABASE"],
                    """
                    INSERT INTO users (username, display_name, password_hash, role)
                    VALUES (?, ?, ?, 'admin')
                    """,
                    (username, display_name, generate_password_hash(password)),
                )
                flash("Administrador criado. Entre com a nova conta.", "success")
                return redirect(url_for("login"))
        return render_template("access.html", mode="setup")

    @app.route("/entrar", methods=["GET", "POST"])
    def login():
        if not query_one(app.config["DATABASE"], "SELECT COUNT(*) AS total FROM users")["total"]:
            return redirect(url_for("first_access"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()[:40]
            password = request.form.get("password", "")
            remote_addr = (request.remote_addr or "desconhecido")[:80]
            minutes = int(app.config["LOGIN_WINDOW_MINUTES"])
            window = f"-{minutes} minutes"
            execute(
                app.config["DATABASE"],
                "DELETE FROM login_attempts WHERE attempted_at < datetime('now', ?)",
                (window,),
            )
            account_failures = query_one(
                app.config["DATABASE"],
                """
                SELECT COUNT(*) AS total FROM login_attempts
                 WHERE username=? AND attempted_at >= datetime('now', ?)
                """,
                (username, window),
            )["total"]
            ip_failures = query_one(
                app.config["DATABASE"],
                """
                SELECT COUNT(*) AS total FROM login_attempts
                 WHERE remote_addr=? AND attempted_at >= datetime('now', ?)
                """,
                (remote_addr, window),
            )["total"]
            if account_failures >= app.config["LOGIN_MAX_ATTEMPTS"] or ip_failures >= app.config[
                "LOGIN_MAX_IP_ATTEMPTS"
            ]:
                flash(f"Muitas tentativas. Aguarde {minutes} minutos.", "error")
                return render_template("access.html", mode="login"), 429

            user = query_one(
                app.config["DATABASE"],
                "SELECT * FROM users WHERE username=? AND active=1",
                (username,),
            )
            if user and check_password_hash(user["password_hash"], password):
                execute(
                    app.config["DATABASE"],
                    "DELETE FROM login_attempts WHERE username=?",
                    (username,),
                )
                session.clear()
                session["user_id"] = user["id"]
                session["session_version"] = user["session_version"]
                session.permanent = True
                return redirect(url_for("dashboard"))

            execute(
                app.config["DATABASE"],
                "INSERT INTO login_attempts (username, remote_addr) VALUES (?, ?)",
                (username, remote_addr),
            )
            flash("Usuário ou senha incorretos.", "error")
        return render_template("access.html", mode="login")

    @app.post("/sair")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def dashboard():
        database = app.config["DATABASE"]
        now = datetime.now().isoformat(timespec="minutes")
        month_limit = (datetime.now() + timedelta(days=30)).isoformat(timespec="minutes")
        stats = {
            "clients": query_one(database, "SELECT COUNT(*) AS total FROM clients WHERE active=1")["total"],
            "events": query_one(database, "SELECT COUNT(*) AS total FROM events WHERE status='active'")["total"],
            "hearings": query_one(
                database,
                """
                SELECT COUNT(*) AS total FROM events
                 WHERE status='active' AND event_type='audiencia' AND start_at BETWEEN ? AND ?
                """,
                (now, month_limit),
            )["total"],
            "users": query_one(database, "SELECT COUNT(*) AS total FROM users WHERE active=1")["total"],
        }
        upcoming = query_all(
            database,
            """
            SELECT e.*, c.full_name AS client_name
              FROM events e LEFT JOIN clients c ON c.id=e.client_id
             WHERE e.status='active' AND e.start_at >= ?
             ORDER BY e.start_at LIMIT 6
            """,
            (now,),
        )
        overdue = query_all(
            database,
            """
            SELECT e.*, c.full_name AS client_name
              FROM events e LEFT JOIN clients c ON c.id=e.client_id
             WHERE e.status='active' AND e.start_at < ?
             ORDER BY e.start_at
            """,
            (now,),
        )
        recent_clients = query_all(
            database,
            "SELECT * FROM clients WHERE active=1 ORDER BY id DESC LIMIT 5",
        )
        return render_template(
            "dashboard.html",
            stats=stats,
            upcoming=upcoming,
            overdue=overdue,
            recent_clients=recent_clients,
        )

    @app.route("/clientes", methods=["GET", "POST"])
    def clients():
        database = app.config["DATABASE"]
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()[:120]
            signed_on = request.form.get("contract_signed_on", "")
            stage = request.form.get("procedural_stage", "").strip()[:180]
            try:
                date.fromisoformat(signed_on)
            except ValueError:
                signed_on = ""
            if not full_name or not signed_on:
                flash("Nome e data de assinatura são obrigatórios.", "error")
            else:
                execute(
                    database,
                    """
                    INSERT INTO clients
                        (full_name, contract_signed_on, procedural_stage, created_by_user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (full_name, signed_on, stage, current_user_id()),
                )
                flash("Cliente cadastrado.", "success")
                return redirect(url_for("clients"))

        search = request.args.get("q", "").strip()[:80]
        params: tuple[Any, ...] = ()
        condition = "c.active=1"
        if search:
            condition += " AND (c.full_name LIKE ? OR c.procedural_stage LIKE ?)"
            term = f"%{search}%"
            params = (term, term)
        rows = query_all(
            database,
            f"""
            SELECT c.*,
                   (SELECT MIN(e.start_at) FROM events e
                     WHERE e.client_id=c.id AND e.status='active'
                       AND e.event_type='audiencia' AND datetime(e.start_at) >= CURRENT_TIMESTAMP
                   ) AS next_hearing_at
              FROM clients c WHERE {condition}
             ORDER BY c.full_name COLLATE NOCASE
            """,
            params,
        )
        return render_template("clients.html", clients=rows, search=search)

    @app.post("/clientes/<int:client_id>/editar")
    def edit_client(client_id: int):
        database = app.config["DATABASE"]
        client = query_one(database, "SELECT id FROM clients WHERE id=? AND active=1", (client_id,))
        if not client:
            abort(404)
        full_name = request.form.get("full_name", "").strip()[:120]
        signed_on = request.form.get("contract_signed_on", "")
        stage = request.form.get("procedural_stage", "").strip()[:180]
        try:
            date.fromisoformat(signed_on)
        except ValueError:
            flash("Confira a data de assinatura.", "error")
            return redirect(url_for("clients"))
        if not full_name:
            flash("Informe o nome do cliente.", "error")
            return redirect(url_for("clients"))
        execute(
            database,
            """
            UPDATE clients SET full_name=?, contract_signed_on=?, procedural_stage=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (full_name, signed_on, stage, client_id),
        )
        flash("Cadastro atualizado.", "success")
        return redirect(url_for("clients"))

    @app.post("/clientes/<int:client_id>/arquivar")
    @admin_required
    def archive_client(client_id: int):
        if request.form.get("confirm_id") != str(client_id):
            abort(400, description="O arquivamento não foi confirmado.")
        execute(
            app.config["DATABASE"],
            "UPDATE clients SET active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (client_id,),
        )
        flash("Cliente arquivado. Os compromissos foram preservados.", "success")
        return redirect(url_for("clients"))

    @app.route("/agenda", methods=["GET", "POST"])
    def agenda():
        database = app.config["DATABASE"]
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:140]
            event_type = request.form.get("event_type", "outro")
            start_at = request.form.get("start_at", "")
            end_at = request.form.get("end_at") or None
            client_id = request.form.get("client_id") or None
            if event_type not in EVENT_TYPES:
                event_type = "outro"
            try:
                parsed_start = datetime.fromisoformat(start_at)
                parsed_end = datetime.fromisoformat(end_at) if end_at else None
                if parsed_end and parsed_end <= parsed_start:
                    raise ValueError
            except ValueError:
                flash("Confira as datas; o término deve ser posterior ao início.", "error")
                return redirect(url_for("agenda"))
            if not title:
                flash("Informe o título do compromisso.", "error")
                return redirect(url_for("agenda"))
            if client_id and not query_one(
                database, "SELECT id FROM clients WHERE id=? AND active=1", (client_id,)
            ):
                client_id = None
            execute(
                database,
                """
                INSERT INTO events
                    (title, event_type, start_at, end_at, location, description,
                     client_id, created_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    event_type,
                    start_at,
                    end_at,
                    request.form.get("location", "").strip()[:120],
                    request.form.get("description", "").strip()[:1000],
                    client_id,
                    current_user_id(),
                ),
            )
            flash("Compromisso salvo.", "success")
            return redirect(url_for("agenda"))

        events = query_all(
            database,
            """
            SELECT e.*, c.full_name AS client_name
              FROM events e LEFT JOIN clients c ON c.id=e.client_id
             WHERE e.status='active' ORDER BY e.start_at
            """,
        )
        client_options = query_all(
            database,
            "SELECT id, full_name FROM clients WHERE active=1 ORDER BY full_name COLLATE NOCASE",
        )
        return render_template("agenda.html", events=events, clients=client_options)

    @app.post("/agenda/<int:event_id>/concluir")
    def complete_event(event_id: int):
        event = query_one(
            app.config["DATABASE"], "SELECT id FROM events WHERE id=? AND status='active'", (event_id,)
        )
        if not event:
            abort(404)
        execute(
            app.config["DATABASE"], "UPDATE events SET status='completed' WHERE id=?", (event_id,)
        )
        flash("Compromisso marcado como concluído.", "success")
        return redirect(url_for("agenda"))

    @app.route("/usuarios", methods=["GET", "POST"])
    @admin_required
    def users():
        database = app.config["DATABASE"]
        if request.method == "POST":
            username = request.form.get("username", "").strip()[:40]
            display_name = request.form.get("display_name", "").strip()[:100]
            role = request.form.get("role", "advogado")
            password = request.form.get("password", "")
            confirmation = request.form.get("confirmation", "")
            if len(username) < 3 or not username.replace("_", "").isalnum():
                flash("Use ao menos 3 letras ou números no usuário.", "error")
            elif len(display_name) < 3:
                flash("Informe o nome completo.", "error")
            elif role not in {"admin", "advogado"}:
                flash("Perfil inválido.", "error")
            elif len(password) < 12:
                flash("A senha precisa ter ao menos 12 caracteres.", "error")
            elif password != confirmation:
                flash("As senhas não conferem.", "error")
            else:
                try:
                    execute(
                        database,
                        """
                        INSERT INTO users (username, display_name, password_hash, role)
                        VALUES (?, ?, ?, ?)
                        """,
                        (username, display_name, generate_password_hash(password), role),
                    )
                    flash("Usuário cadastrado.", "success")
                    return redirect(url_for("users"))
                except sqlite3.IntegrityError:
                    flash("Esse usuário já existe.", "error")
        rows = query_all(
            database,
            "SELECT id, username, display_name, role, active, created_at FROM users ORDER BY display_name COLLATE NOCASE",
        )
        return render_template("users.html", users=rows)

    @app.post("/usuarios/<int:user_id>/status")
    @admin_required
    def change_user_status(user_id: int):
        database = app.config["DATABASE"]
        target = query_one(database, "SELECT * FROM users WHERE id=?", (user_id,))
        if not target:
            abort(404)
        if user_id == current_user_id():
            flash("Você não pode desativar a própria conta.", "error")
            return redirect(url_for("users"))
        if target["role"] == "admin" and target["active"]:
            active_admins = query_one(
                database, "SELECT COUNT(*) AS total FROM users WHERE role='admin' AND active=1"
            )["total"]
            if active_admins <= 1:
                flash("O sistema precisa manter um administrador ativo.", "error")
                return redirect(url_for("users"))
        new_status = 0 if target["active"] else 1
        execute(
            database,
            "UPDATE users SET active=?, session_version=session_version+1 WHERE id=?",
            (new_status, user_id),
        )
        flash("Status do usuário atualizado.", "success")
        return redirect(url_for("users"))

    @app.post("/usuarios/<int:user_id>/senha")
    @admin_required
    def reset_user_password(user_id: int):
        database = app.config["DATABASE"]
        if not query_one(database, "SELECT id FROM users WHERE id=?", (user_id,)):
            abort(404)
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")
        if len(password) < 12:
            flash("A nova senha precisa ter ao menos 12 caracteres.", "error")
        elif password != confirmation:
            flash("As senhas não conferem.", "error")
        else:
            execute(
                database,
                "UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?",
                (generate_password_hash(password), user_id),
            )
            flash("Senha atualizada e sessões anteriores encerradas.", "success")
        return redirect(url_for("users"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
