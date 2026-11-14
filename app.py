import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, request
from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.engine import make_url
from werkzeug.exceptions import HTTPException

from extensions import db
from models import Account, Transfer


ACCOUNT_KINDS = {"cash", "bank", "credit_card", "broker"}
CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")


def request_json_object():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def parse_decimal(value, field_name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name}必須是數字。")

    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{field_name}格式不正確。") from error

    if not parsed.is_finite():
        raise ValueError(f"{field_name}必須是有限數值。")

    return parsed


def parse_currency(value):
    if not isinstance(value, str) or CURRENCY_PATTERN.fullmatch(value) is None:
        raise ValueError("幣別必須是三碼大寫英文字母。")

    return value


def parse_day(value, field_name):
    if type(value) is not int or not 1 <= value <= 31:
        raise ValueError(f"{field_name}必須是 1 到 31 的整數。")

    return value


def parse_iso_date(value):
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
    ):
        raise ValueError("移轉日期必須使用 YYYY-MM-DD 格式。")

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("移轉日期不是有效日期。") from error


def serialize_account(account):
    return {
        "id": account.id,
        "name": account.name,
        "kind": account.kind,
        "currency": account.currency,
        "opening_balance": str(account.opening_balance),
        "statement_day": account.statement_day,
        "payment_day": account.payment_day,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
    }


def serialize_transfer(transfer):
    return {
        "id": transfer.id,
        "transferred_on": transfer.transferred_on.isoformat(),
        "amount": str(transfer.amount),
        "currency": transfer.currency,
        "fx_rate_to_twd": str(transfer.fx_rate_to_twd),
        "from_account_id": transfer.from_account_id,
        "to_account_id": transfer.to_account_id,
        "note": transfer.note,
        "created_at": transfer.created_at.isoformat(),
        "updated_at": transfer.updated_at.isoformat(),
    }


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

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        db.session.rollback()
        current_app.logger.info(
            "Request rejected by database integrity validation: %s",
            type(error).__name__,
        )
        return json_response(400, "資料內容違反規則，請檢查輸入欄位。", None)

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error):
        db.session.rollback()
        current_app.logger.error(
            "Database operation failed: %s",
            type(error).__name__,
            exc_info=True,
        )
        return json_response(500, "資料庫暫時無法連線，請稍後再試。", None)

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

    @app.get("/api/accounts")
    def list_accounts():
        accounts = Account.query.order_by(Account.id).all()
        return json_response(
            200,
            "帳戶清單取得成功。",
            [serialize_account(account) for account in accounts],
        )

    @app.post("/api/accounts")
    def create_account():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return json_response(400, "帳戶名稱為必填欄位。", None)
        name = name.strip()

        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in ACCOUNT_KINDS:
            return json_response(400, "帳戶種類不正確。", None)

        try:
            if "currency" not in payload:
                currency = "TWD"
            else:
                if payload["currency"] is None:
                    raise ValueError("幣別不可為空。")
                currency = parse_currency(payload["currency"])

            opening_balance = None
            if "opening_balance" in payload:
                if payload["opening_balance"] is None:
                    raise ValueError("期初金額不可為空。")
                opening_balance = parse_decimal(
                    payload["opening_balance"],
                    "期初金額",
                )

            statement_day = payload.get("statement_day")
            if statement_day is not None:
                statement_day = parse_day(statement_day, "結帳日")

            payment_day = payload.get("payment_day")
            if payment_day is not None:
                payment_day = parse_day(payment_day, "繳款日")
        except ValueError as error:
            return json_response(400, str(error), None)

        if db.session.query(Account.id).filter(Account.name == name).first():
            return json_response(400, "帳戶名稱已存在。", None)

        account = Account(
            name=name,
            kind=kind,
            currency=currency,
            statement_day=statement_day,
            payment_day=payment_day,
        )
        if opening_balance is not None:
            account.opening_balance = opening_balance

        db.session.add(account)
        db.session.flush()
        db.session.refresh(account)
        data = serialize_account(account)
        db.session.commit()

        return json_response(201, "帳戶新增成功。", data)

    @app.get("/api/accounts/<int:account_id>")
    def get_account(account_id):
        account = db.session.get(Account, account_id)
        if account is None:
            return json_response(404, "找不到這個帳戶。", None)

        return json_response(200, "帳戶資料取得成功。", serialize_account(account))

    @app.patch("/api/accounts/<int:account_id>")
    def update_account(account_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        account = db.session.get(Account, account_id)
        if account is None:
            return json_response(404, "找不到這個帳戶。", None)

        updates = {}
        if "name" in payload:
            name = payload["name"]
            if not isinstance(name, str) or not name.strip():
                return json_response(400, "帳戶名稱不可為空。", None)
            updates["name"] = name.strip()

        for field, label in (
            ("statement_day", "結帳日"),
            ("payment_day", "繳款日"),
        ):
            value = payload.get(field)
            if value is not None:
                try:
                    updates[field] = parse_day(value, label)
                except ValueError as error:
                    return json_response(400, str(error), None)

        if not updates:
            return json_response(400, "請提供至少一個可更新欄位。", None)

        if "name" in updates and db.session.query(Account.id).filter(
            Account.name == updates["name"],
            Account.id != account_id,
        ).first():
            return json_response(400, "帳戶名稱已存在。", None)

        for field, value in updates.items():
            setattr(account, field, value)
        account.updated_at = func.now()

        db.session.flush()
        db.session.refresh(account)
        data = serialize_account(account)
        db.session.commit()

        return json_response(200, "帳戶更新成功。", data)

    @app.get("/api/accounts/<int:account_id>/balance")
    def get_account_balance(account_id):
        account = db.session.get(Account, account_id)
        if account is None:
            return json_response(404, "找不到這個帳戶。", None)

        signed_amount = case(
            (Transfer.to_account_id == account_id, Transfer.amount),
            else_=-Transfer.amount,
        )
        signed_amount_twd = signed_amount * Transfer.fx_rate_to_twd
        totals = db.session.query(
            func.coalesce(func.sum(signed_amount), 0),
            func.coalesce(func.sum(signed_amount_twd), 0),
        ).filter(
            or_(
                Transfer.from_account_id == account_id,
                Transfer.to_account_id == account_id,
            )
        ).one()

        balance = account.opening_balance + totals[0]
        # The schema has no opening-balance FX rate; treat that amount as TWD 1:1.
        balance_twd = account.opening_balance + totals[1]
        return json_response(
            200,
            "帳戶餘額取得成功。",
            {
                "account_id": account.id,
                "currency": account.currency,
                "balance": str(balance),
                "balance_twd": str(balance_twd),
            },
        )

    @app.post("/api/transfers")
    def create_transfer():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = (
            "transferred_on",
            "amount",
            "currency",
            "fx_rate_to_twd",
            "from_account_id",
            "to_account_id",
        )
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "移轉的必填欄位不可缺少或為空。", None)

        try:
            transferred_on = parse_iso_date(payload["transferred_on"])
            amount = parse_decimal(payload["amount"], "移轉金額")
            if amount <= 0:
                raise ValueError("移轉金額必須大於 0。")

            currency = parse_currency(payload["currency"])
            fx_rate_to_twd = parse_decimal(
                payload["fx_rate_to_twd"],
                "台幣匯率",
            )
            if fx_rate_to_twd <= 0:
                raise ValueError("台幣匯率必須大於 0。")

            from_account_id = payload["from_account_id"]
            to_account_id = payload["to_account_id"]
            if type(from_account_id) is not int or type(to_account_id) is not int:
                raise ValueError("轉出與轉入帳戶編號必須是整數。")
            if from_account_id == to_account_id:
                raise ValueError("轉出帳戶與轉入帳戶不可相同。")

            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                raise ValueError("備註必須是文字。")
        except ValueError as error:
            return json_response(400, str(error), None)

        from_account = db.session.get(Account, from_account_id)
        to_account = db.session.get(Account, to_account_id)
        if from_account is None or to_account is None:
            return json_response(400, "轉出或轉入帳戶不存在。", None)
        if from_account.currency != currency or to_account.currency != currency:
            return json_response(
                400,
                "移轉幣別必須與轉出及轉入帳戶的幣別相同。",
                None,
            )

        transfer = Transfer(
            transferred_on=transferred_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate_to_twd,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            note=note,
        )
        db.session.add(transfer)
        db.session.flush()
        db.session.refresh(transfer)
        data = serialize_transfer(transfer)
        db.session.commit()

        return json_response(201, "移轉新增成功。", data)

    @app.get("/api/transfers")
    def list_transfers():
        transfers = Transfer.query.order_by(Transfer.id).all()
        return json_response(
            200,
            "移轉清單取得成功。",
            [serialize_transfer(transfer) for transfer in transfers],
        )

    @app.get("/api/transfers/<int:transfer_id>")
    def get_transfer(transfer_id):
        transfer = db.session.get(Transfer, transfer_id)
        if transfer is None:
            return json_response(404, "找不到這筆移轉。", None)

        return json_response(
            200,
            "移轉資料取得成功。",
            serialize_transfer(transfer),
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
