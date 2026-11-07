import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url
from werkzeug.exceptions import HTTPException

from extensions import db


def json_response(code, message, data):
    return jsonify(
        {
            "code": code,
            "message": message,
            "data": data,
        }
    ), code


def create_app():
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in the environment or project .env file."
        )

    database_uri = make_url(database_url)
    if database_uri.drivername in {"postgres", "postgresql"}:
        database_url = database_uri.set(
            drivername="postgresql+psycopg2"
        ).render_as_string(hide_password=False)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        code = error.code or 500
        message = {
            400: "請求格式錯誤。",
            404: "找不到這一筆",
            405: "不支援此 HTTP 方法。",
        }.get(code, error.description)

        return json_response(code, message, None)

    @app.get("/api/health")
    def health_check():
        return json_response(
            200,
            "伺服器運作正常，測試正常可以進行其他任務。",
            {
                "status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.get("/api/health/db")
    def database_health_check():
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            current_app.logger.exception("Database health check failed")
            return json_response(500, "資料庫暫時連不上", None)

        return json_response(200, "資料庫連線正常", {"status": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
