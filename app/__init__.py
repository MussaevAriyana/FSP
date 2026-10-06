"""ФСП Карьера — платформа подбора ИТ-специалистов с верифицированным профилем достижений."""
import logging
import os

from flask import Flask, send_from_directory

from . import db as D
from .apidoc import Api
from .config import Config


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"), static_url_path="/static")
    app.json.sort_keys = False
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # PDF резюме — не более 5 МБ
    app.json.ensure_ascii = False
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    os.makedirs(os.path.dirname(app.config["DB_PATH"]) or ".", exist_ok=True)
    D.init_db(app.config["DB_PATH"])
    app.teardown_appcontext(D.close_db)

    api = Api(app, "ФСП Карьера API", "1.0.0",
              "REST API платформы подбора ИТ-специалистов. Авторизация — Bearer JWT (получить: POST /api/auth/login). "
              "Ошибки: {error, message, details?}.")
    from .routers import auth, candidate, employer, public
    for mod in (public, auth, candidate, employer):
        mod.register(api)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if resp.mimetype == "application/json":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    app.extensions["api"] = api
    return app
