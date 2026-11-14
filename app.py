import calendar
import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, request
from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.engine import make_url
from werkzeug.exceptions import HTTPException

from extensions import db
from models import (
    Account,
    DrawPeriod,
    DrawPrize,
    Expense,
    ExpenseCategory,
    Income,
    IncomeCategory,
    Invoice,
    InvoiceItem,
    Transfer,
)


ACCOUNT_KINDS = {"cash", "bank", "credit_card", "broker"}
CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")
INVOICE_KINDS = {"paper", "electronic"}
PRIZE_STATUSES = {"unchecked", "lost", "won", "claimed", "void"}
DRAW_PRIZE_TIERS = {
    "special",
    "grand",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "extra_sixth",
}
FULL_NUMBER_TIERS = {"special", "grand", "first"}


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


def parse_iso_date(value, field_name="移轉日期"):
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
    ):
        raise ValueError(f"{field_name}必須使用 YYYY-MM-DD 格式。")

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name}不是有效日期。") from error


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def invoice_period_key(issued_on):
    first_month = ((issued_on.month - 1) // 2) * 2 + 1
    return f"{issued_on.year:04d}-{first_month:02d}"


def period_date_range(period_key):
    if not isinstance(period_key, str) or re.fullmatch(
        r"[0-9]{4}-(01|03|05|07|09|11)",
        period_key,
    ) is None:
        raise ValueError("期別必須是 YYYY-01、YYYY-03 等雙月期格式。")

    year, month = (int(part) for part in period_key.split("-"))
    try:
        start = date(year, month, 1)
    except ValueError as error:
        raise ValueError("期別不是有效日期。") from error

    if month == 11:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 2, 1) - timedelta(days=1)
    return start, end


def find_matching_prize(invoice_number, prizes):
    invoice_digits = invoice_number[2:]
    tier_order = {
        "special": 0,
        "grand": 1,
        "first": 2,
        "second": 3,
        "third": 4,
        "fourth": 5,
        "fifth": 6,
        "sixth": 7,
        "extra_sixth": 8,
    }
    matches = []
    for prize in prizes:
        if prize.tier in FULL_NUMBER_TIERS:
            is_match = invoice_digits == prize.matching_number
        else:
            is_match = invoice_digits.endswith(prize.matching_number)
        if is_match:
            matches.append(prize)

    if not matches:
        return None
    return min(
        matches,
        key=lambda prize: (
            tier_order[prize.tier],
            -len(prize.matching_number),
            prize.id,
        ),
    )


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


def serialize_income_category(category):
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "created_at": category.created_at.isoformat(),
        "updated_at": category.updated_at.isoformat(),
    }


def serialize_income(income):
    return {
        "id": income.id,
        "received_on": income.received_on.isoformat(),
        "amount": str(income.amount),
        "currency": income.currency,
        "fx_rate_to_twd": str(income.fx_rate_to_twd),
        "category_id": income.category_id,
        "account_id": income.account_id,
        "source": income.source,
        "note": income.note,
        "invoice_id": income.invoice_id,
        "created_at": income.created_at.isoformat(),
        "updated_at": income.updated_at.isoformat(),
    }


def serialize_invoice(invoice):
    return {
        "id": invoice.id,
        "number": invoice.number,
        "issued_on": invoice.issued_on.isoformat(),
        "amount": str(invoice.amount),
        "kind": invoice.kind,
        "currency": invoice.currency,
        "fx_rate_to_twd": str(invoice.fx_rate_to_twd),
        "random_code": invoice.random_code,
        "seller_name": invoice.seller_name,
        "seller_ban": invoice.seller_ban,
        "prize_status": invoice.prize_status,
        "created_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
    }


def serialize_invoice_item(item):
    return {
        "id": item.id,
        "invoice_id": item.invoice_id,
        "name": item.name,
        "quantity": str(item.quantity),
        "unit_price": str(item.unit_price),
        "line_amount": str(item.line_amount),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def serialize_draw_prize(prize):
    return {
        "id": prize.id,
        "draw_period_id": prize.draw_period_id,
        "tier": prize.tier,
        "matching_number": prize.matching_number,
        "amount": str(prize.amount),
    }


def serialize_expense_category(category):
    return {
        "id": category.id,
        "name": category.name,
        "created_at": category.created_at.isoformat(),
        "updated_at": category.updated_at.isoformat(),
    }


def serialize_expense(expense):
    return {
        "id": expense.id,
        "spent_on": expense.spent_on.isoformat(),
        "amount": str(expense.amount),
        "currency": expense.currency,
        "fx_rate_to_twd": str(expense.fx_rate_to_twd),
        "category_id": expense.category_id,
        "account_id": expense.account_id,
        "merchant": expense.merchant,
        "note": expense.note,
        "invoice_id": expense.invoice_id,
        "settled_on": (
            expense.settled_on.isoformat() if expense.settled_on else None
        ),
        "created_at": expense.created_at.isoformat(),
        "updated_at": expense.updated_at.isoformat(),
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
        income_totals = db.session.query(
            func.coalesce(func.sum(Income.amount), 0),
            func.coalesce(
                func.sum(Income.amount * Income.fx_rate_to_twd),
                0,
            ),
        ).filter(Income.account_id == account_id).one()
        expense_totals = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0),
            func.coalesce(
                func.sum(Expense.amount * Expense.fx_rate_to_twd),
                0,
            ),
        ).filter(Expense.account_id == account_id).one()

        balance = (
            account.opening_balance
            + totals[0]
            + income_totals[0]
            - expense_totals[0]
        )
        # The schema has no opening-balance FX rate; treat that amount as TWD 1:1.
        balance_twd = (
            account.opening_balance
            + totals[1]
            + income_totals[1]
            - expense_totals[1]
        )
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

    @app.get("/api/summary")
    def get_monthly_summary():
        month = request.args.get("month")
        if month is None or re.fullmatch(
            r"[0-9]{4}-(0[1-9]|1[0-2])",
            month,
        ) is None:
            return json_response(400, "請提供 YYYY-MM 格式的月份。", None)

        try:
            month_start = date.fromisoformat(f"{month}-01")
        except ValueError:
            return json_response(400, "月份不是有效日期。", None)
        month_end = date(
            month_start.year,
            month_start.month,
            calendar.monthrange(month_start.year, month_start.month)[1],
        )

        income_twd = db.session.query(
            func.coalesce(
                func.sum(Income.amount * Income.fx_rate_to_twd),
                0,
            )
        ).filter(
            Income.received_on >= month_start,
            Income.received_on <= month_end,
        ).scalar()
        expense_twd = db.session.query(
            func.coalesce(
                func.sum(Expense.amount * Expense.fx_rate_to_twd),
                0,
            )
        ).filter(
            Expense.spent_on >= month_start,
            Expense.spent_on <= month_end,
        ).scalar()

        return json_response(
            200,
            "月收支摘要取得成功。",
            {
                "month": month,
                "income_twd": str(income_twd),
                "expense_twd": str(expense_twd),
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

    @app.get("/api/income-categories")
    def list_income_categories():
        categories = IncomeCategory.query.order_by(IncomeCategory.id).all()
        return json_response(
            200,
            "入帳分類清單取得成功。",
            [serialize_income_category(category) for category in categories],
        )

    @app.post("/api/income-categories")
    def create_income_category():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return json_response(400, "分類名稱為必填欄位。", None)
        name = name.strip()

        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            return json_response(400, "分類說明必須是文字或 null。", None)

        if db.session.query(IncomeCategory.id).filter(
            IncomeCategory.name == name
        ).first():
            return json_response(400, "這個入帳分類名稱已存在。", None)

        category = IncomeCategory(name=name, description=description)
        db.session.add(category)
        db.session.flush()
        db.session.refresh(category)
        data = serialize_income_category(category)
        db.session.commit()

        return json_response(201, "入帳分類新增成功。", data)

    @app.get("/api/income-categories/<int:category_id>")
    def get_income_category(category_id):
        category = db.session.get(IncomeCategory, category_id)
        if category is None:
            return json_response(404, "找不到這個入帳分類。", None)

        return json_response(
            200,
            "入帳分類資料取得成功。",
            serialize_income_category(category),
        )

    @app.patch("/api/income-categories/<int:category_id>")
    def update_income_category(category_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        category = db.session.get(IncomeCategory, category_id)
        if category is None:
            return json_response(404, "找不到這個入帳分類。", None)

        updates = {}
        if "name" in payload:
            name = payload["name"]
            if not isinstance(name, str) or not name.strip():
                return json_response(400, "分類名稱不可為空。", None)
            updates["name"] = name.strip()

        if "description" in payload:
            description = payload["description"]
            if description is not None and not isinstance(description, str):
                return json_response(400, "分類說明必須是文字或 null。", None)
            updates["description"] = description

        if not updates:
            return json_response(400, "請提供至少一個可更新欄位。", None)

        if "name" in updates and db.session.query(IncomeCategory.id).filter(
            IncomeCategory.name == updates["name"],
            IncomeCategory.id != category_id,
        ).first():
            return json_response(400, "這個入帳分類名稱已存在。", None)

        for field, value in updates.items():
            setattr(category, field, value)
        category.updated_at = func.now()

        db.session.flush()
        db.session.refresh(category)
        data = serialize_income_category(category)
        db.session.commit()

        return json_response(200, "入帳分類更新成功。", data)

    @app.get("/api/incomes")
    def list_incomes():
        filters = []
        for parameter, column, label in (
            ("account_id", Income.account_id, "帳戶編號"),
            ("category_id", Income.category_id, "分類編號"),
        ):
            value = request.args.get(parameter)
            if value is not None:
                if re.fullmatch(r"\d+", value) is None or int(value) < 1:
                    return json_response(
                        400,
                        f"{label}必須是正整數。",
                        None,
                    )
                filters.append(column == int(value))

        date_from = request.args.get("date_from")
        parsed_date_from = None
        if date_from is not None:
            try:
                parsed_date_from = parse_iso_date(date_from, "起始日期")
            except ValueError as error:
                return json_response(400, str(error), None)

        date_to = request.args.get("date_to")
        parsed_date_to = None
        if date_to is not None:
            try:
                parsed_date_to = parse_iso_date(date_to, "結束日期")
            except ValueError as error:
                return json_response(400, str(error), None)

        if (
            parsed_date_from is not None
            and parsed_date_to is not None
            and parsed_date_from > parsed_date_to
        ):
            return json_response(400, "起始日期不可晚於結束日期。", None)
        if parsed_date_from is not None:
            filters.append(Income.received_on >= parsed_date_from)
        if parsed_date_to is not None:
            filters.append(Income.received_on <= parsed_date_to)

        incomes = Income.query.filter(*filters).order_by(Income.id).all()
        return json_response(
            200,
            "入帳清單取得成功。",
            [serialize_income(income) for income in incomes],
        )

    @app.post("/api/incomes")
    def create_income():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = (
            "received_on",
            "amount",
            "currency",
            "fx_rate_to_twd",
            "category_id",
            "account_id",
        )
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "入帳的必填欄位不可缺少或為空。", None)

        try:
            received_on = parse_iso_date(payload["received_on"], "入帳日期")
            amount = parse_decimal(payload["amount"], "入帳金額")
            if amount <= 0:
                raise ValueError("入帳金額必須大於 0。")

            currency = parse_currency(payload["currency"])
            fx_rate_to_twd = parse_decimal(
                payload["fx_rate_to_twd"],
                "台幣匯率",
            )
            if fx_rate_to_twd <= 0:
                raise ValueError("台幣匯率必須大於 0。")

            category_id = payload["category_id"]
            account_id = payload["account_id"]
            if type(category_id) is not int or type(account_id) is not int:
                raise ValueError("分類與帳戶編號必須是整數。")

            source = payload.get("source")
            note = payload.get("note")
            if source is not None and not isinstance(source, str):
                raise ValueError("來源必須是文字或 null。")
            if note is not None and not isinstance(note, str):
                raise ValueError("備註必須是文字或 null。")
            if not has_text(source) and not has_text(note):
                raise ValueError("來源與備註至少需填寫一項。")

            invoice_id = payload.get("invoice_id")
            if invoice_id is not None and type(invoice_id) is not int:
                raise ValueError("發票編號必須是整數或 null。")
        except ValueError as error:
            return json_response(400, str(error), None)

        category = db.session.get(IncomeCategory, category_id)
        account = db.session.get(Account, account_id)
        if category is None:
            return json_response(400, "指定的入帳分類不存在。", None)
        if account is None:
            return json_response(400, "指定的帳戶不存在。", None)
        if account.currency != currency:
            return json_response(400, "入帳幣別必須與帳戶幣別相同。", None)

        if invoice_id is not None:
            if db.session.get(Invoice, invoice_id) is None:
                return json_response(400, "指定的發票不存在。", None)
            if db.session.query(Income.id).filter(
                Income.invoice_id == invoice_id
            ).first():
                return json_response(400, "這張發票已連結入帳。", None)

        income = Income(
            received_on=received_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate_to_twd,
            category_id=category_id,
            account_id=account_id,
            source=source,
            note=note,
            invoice_id=invoice_id,
        )
        db.session.add(income)
        db.session.flush()
        db.session.refresh(income)
        data = serialize_income(income)
        db.session.commit()

        return json_response(201, "入帳新增成功。", data)

    @app.get("/api/incomes/<int:income_id>")
    def get_income(income_id):
        income = db.session.get(Income, income_id)
        if income is None:
            return json_response(404, "找不到這筆入帳。", None)

        return json_response(200, "入帳資料取得成功。", serialize_income(income))

    @app.patch("/api/incomes/<int:income_id>")
    def update_income(income_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        income = db.session.get(Income, income_id)
        if income is None:
            return json_response(404, "找不到這筆入帳。", None)

        updates = {}
        try:
            for field, label in (
                ("received_on", "入帳日期"),
                ("amount", "入帳金額"),
                ("fx_rate_to_twd", "台幣匯率"),
                ("category_id", "分類編號"),
                ("account_id", "帳戶編號"),
                ("currency", "幣別"),
                ("source", "來源"),
                ("note", "備註"),
            ):
                if field not in payload:
                    continue
                value = payload[field]
                if value is None and field in {"source", "note"}:
                    continue
                if value is None:
                    raise ValueError(f"{label}不可為空。")

                if field == "received_on":
                    updates[field] = parse_iso_date(value, label)
                elif field in {"amount", "fx_rate_to_twd"}:
                    value = parse_decimal(value, label)
                    if value <= 0:
                        raise ValueError(f"{label}必須大於 0。")
                    updates[field] = value
                elif field in {"category_id", "account_id"}:
                    if type(value) is not int:
                        raise ValueError(f"{label}必須是整數。")
                    updates[field] = value
                elif field == "currency":
                    updates[field] = parse_currency(value)
                elif not isinstance(value, str):
                    raise ValueError(f"{label}必須是文字或 null。")
                else:
                    updates[field] = value
        except ValueError as error:
            return json_response(400, str(error), None)

        if not updates:
            return json_response(400, "請提供至少一個可更新欄位。", None)

        category_id = updates.get("category_id", income.category_id)
        account_id = updates.get("account_id", income.account_id)
        currency = updates.get("currency", income.currency)
        if "category_id" in updates and db.session.get(
            IncomeCategory,
            category_id,
        ) is None:
            return json_response(400, "指定的入帳分類不存在。", None)

        account = None
        if "account_id" in updates or "currency" in updates:
            account = db.session.get(Account, account_id)
            if account is None:
                return json_response(400, "指定的帳戶不存在。", None)
        if account is not None and account.currency != currency:
            return json_response(400, "入帳幣別必須與帳戶幣別相同。", None)

        source = updates.get("source", income.source)
        note = updates.get("note", income.note)
        if not has_text(source) and not has_text(note):
            return json_response(400, "來源與備註至少需填寫一項。", None)

        for field, value in updates.items():
            setattr(income, field, value)
        income.updated_at = func.now()

        db.session.flush()
        db.session.refresh(income)
        data = serialize_income(income)
        db.session.commit()

        return json_response(200, "入帳更新成功。", data)

    @app.get("/api/expense-categories")
    def list_expense_categories():
        categories = ExpenseCategory.query.order_by(ExpenseCategory.id).all()
        return json_response(
            200,
            "花費分類清單取得成功。",
            [serialize_expense_category(category) for category in categories],
        )

    @app.post("/api/expense-categories")
    def create_expense_category():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return json_response(400, "分類名稱為必填欄位。", None)
        name = name.strip()

        if db.session.query(ExpenseCategory.id).filter(
            ExpenseCategory.name == name
        ).first():
            return json_response(400, "這個花費分類名稱已存在。", None)

        category = ExpenseCategory(name=name)
        db.session.add(category)
        db.session.flush()
        db.session.refresh(category)
        data = serialize_expense_category(category)
        db.session.commit()

        return json_response(201, "花費分類新增成功。", data)

    @app.get("/api/expense-categories/<int:category_id>")
    def get_expense_category(category_id):
        category = db.session.get(ExpenseCategory, category_id)
        if category is None:
            return json_response(404, "找不到這個花費分類。", None)

        return json_response(
            200,
            "花費分類資料取得成功。",
            serialize_expense_category(category),
        )

    @app.patch("/api/expense-categories/<int:category_id>")
    def update_expense_category(category_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        category = db.session.get(ExpenseCategory, category_id)
        if category is None:
            return json_response(404, "找不到這個花費分類。", None)

        if "name" not in payload:
            return json_response(400, "請提供要更新的分類名稱。", None)
        name = payload["name"]
        if not isinstance(name, str) or not name.strip():
            return json_response(400, "分類名稱不可為空。", None)
        name = name.strip()

        if db.session.query(ExpenseCategory.id).filter(
            ExpenseCategory.name == name,
            ExpenseCategory.id != category_id,
        ).first():
            return json_response(400, "這個花費分類名稱已存在。", None)

        category.name = name
        category.updated_at = func.now()
        db.session.flush()
        db.session.refresh(category)
        data = serialize_expense_category(category)
        db.session.commit()

        return json_response(200, "花費分類更新成功。", data)

    @app.get("/api/expenses")
    def list_expenses():
        filters = []
        for parameter, column, label in (
            ("account_id", Expense.account_id, "帳戶編號"),
            ("category_id", Expense.category_id, "分類編號"),
            ("invoice_id", Expense.invoice_id, "發票編號"),
        ):
            value = request.args.get(parameter)
            if value is not None:
                if re.fullmatch(r"[0-9]+", value) is None or int(value) < 1:
                    return json_response(400, f"{label}必須是正整數。", None)
                filters.append(column == int(value))

        date_from = request.args.get("date_from")
        parsed_date_from = None
        if date_from is not None:
            try:
                parsed_date_from = parse_iso_date(date_from, "起始日期")
            except ValueError as error:
                return json_response(400, str(error), None)

        date_to = request.args.get("date_to")
        parsed_date_to = None
        if date_to is not None:
            try:
                parsed_date_to = parse_iso_date(date_to, "結束日期")
            except ValueError as error:
                return json_response(400, str(error), None)

        if (
            parsed_date_from is not None
            and parsed_date_to is not None
            and parsed_date_from > parsed_date_to
        ):
            return json_response(400, "起始日期不可晚於結束日期。", None)
        if parsed_date_from is not None:
            filters.append(Expense.spent_on >= parsed_date_from)
        if parsed_date_to is not None:
            filters.append(Expense.spent_on <= parsed_date_to)

        expenses = Expense.query.filter(*filters).order_by(Expense.id).all()
        return json_response(
            200,
            "花費清單取得成功。",
            [serialize_expense(expense) for expense in expenses],
        )

    @app.post("/api/expenses")
    def create_expense():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = (
            "spent_on",
            "amount",
            "currency",
            "fx_rate_to_twd",
            "category_id",
            "account_id",
        )
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "花費的必填欄位不可缺少或為空。", None)

        try:
            spent_on = parse_iso_date(payload["spent_on"], "消費日期")
            amount = parse_decimal(payload["amount"], "花費金額")
            if amount <= 0:
                raise ValueError("花費金額必須大於 0。")

            currency = parse_currency(payload["currency"])
            fx_rate_to_twd = parse_decimal(
                payload["fx_rate_to_twd"],
                "台幣匯率",
            )
            if fx_rate_to_twd <= 0:
                raise ValueError("台幣匯率必須大於 0。")

            category_id = payload["category_id"]
            account_id = payload["account_id"]
            if type(category_id) is not int or type(account_id) is not int:
                raise ValueError("分類與帳戶編號必須是整數。")

            merchant = payload.get("merchant")
            note = payload.get("note")
            if merchant is not None and not isinstance(merchant, str):
                raise ValueError("商家必須是文字或 null。")
            if note is not None and not isinstance(note, str):
                raise ValueError("備註必須是文字或 null。")
            if not has_text(merchant) and not has_text(note):
                raise ValueError("商家與備註至少需填寫一項。")

            invoice_id = payload.get("invoice_id")
            if invoice_id is not None and type(invoice_id) is not int:
                raise ValueError("發票編號必須是整數或 null。")

            settled_on = payload.get("settled_on")
            if settled_on is not None:
                settled_on = parse_iso_date(settled_on, "結算日期")
        except ValueError as error:
            return json_response(400, str(error), None)

        category = db.session.get(ExpenseCategory, category_id)
        account = db.session.get(Account, account_id)
        if category is None:
            return json_response(400, "指定的花費分類不存在。", None)
        if account is None:
            return json_response(400, "指定的帳戶不存在。", None)
        if account.currency != currency:
            return json_response(400, "花費幣別必須與帳戶幣別相同。", None)
        if invoice_id is not None and db.session.get(Invoice, invoice_id) is None:
            return json_response(400, "指定的發票不存在。", None)

        expense = Expense(
            spent_on=spent_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate_to_twd,
            category_id=category_id,
            account_id=account_id,
            merchant=merchant,
            note=note,
            invoice_id=invoice_id,
            settled_on=settled_on,
        )
        db.session.add(expense)
        db.session.flush()
        db.session.refresh(expense)
        data = serialize_expense(expense)
        db.session.commit()

        return json_response(201, "花費新增成功。", data)

    @app.get("/api/expenses/<int:expense_id>")
    def get_expense(expense_id):
        expense = db.session.get(Expense, expense_id)
        if expense is None:
            return json_response(404, "找不到這筆花費。", None)

        return json_response(200, "花費資料取得成功。", serialize_expense(expense))

    @app.patch("/api/expenses/<int:expense_id>")
    def update_expense(expense_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        expense = db.session.get(Expense, expense_id)
        if expense is None:
            return json_response(404, "找不到這筆花費。", None)

        updates = {}
        try:
            for field, label in (
                ("spent_on", "消費日期"),
                ("amount", "花費金額"),
                ("currency", "幣別"),
                ("fx_rate_to_twd", "台幣匯率"),
                ("category_id", "分類編號"),
                ("account_id", "帳戶編號"),
                ("merchant", "商家"),
                ("note", "備註"),
                ("invoice_id", "發票編號"),
                ("settled_on", "結算日期"),
            ):
                if field not in payload:
                    continue
                value = payload[field]
                if value is None and field in {
                    "merchant",
                    "note",
                    "invoice_id",
                    "settled_on",
                }:
                    continue
                if value is None:
                    raise ValueError(f"{label}不可為空。")

                if field in {"spent_on", "settled_on"}:
                    updates[field] = parse_iso_date(value, label)
                elif field in {"amount", "fx_rate_to_twd"}:
                    value = parse_decimal(value, label)
                    if value <= 0:
                        raise ValueError(f"{label}必須大於 0。")
                    updates[field] = value
                elif field in {"category_id", "account_id", "invoice_id"}:
                    if type(value) is not int:
                        raise ValueError(f"{label}必須是整數。")
                    updates[field] = value
                elif field == "currency":
                    updates[field] = parse_currency(value)
                elif not isinstance(value, str):
                    raise ValueError(f"{label}必須是文字或 null。")
                else:
                    updates[field] = value
        except ValueError as error:
            return json_response(400, str(error), None)

        if not updates:
            return json_response(400, "請提供至少一個可更新欄位。", None)

        category_id = updates.get("category_id", expense.category_id)
        account_id = updates.get("account_id", expense.account_id)
        currency = updates.get("currency", expense.currency)
        invoice_id = updates.get("invoice_id", expense.invoice_id)
        if "category_id" in updates and db.session.get(
            ExpenseCategory,
            category_id,
        ) is None:
            return json_response(400, "指定的花費分類不存在。", None)

        account = None
        if "account_id" in updates or "currency" in updates:
            account = db.session.get(Account, account_id)
            if account is None:
                return json_response(400, "指定的帳戶不存在。", None)
        if account is not None and account.currency != currency:
            return json_response(400, "花費幣別必須與帳戶幣別相同。", None)

        if "invoice_id" in updates and db.session.get(
            Invoice,
            invoice_id,
        ) is None:
            return json_response(400, "指定的發票不存在。", None)

        merchant = updates.get("merchant", expense.merchant)
        note = updates.get("note", expense.note)
        if not has_text(merchant) and not has_text(note):
            return json_response(400, "商家與備註至少需填寫一項。", None)

        for field, value in updates.items():
            setattr(expense, field, value)
        expense.updated_at = func.now()

        db.session.flush()
        db.session.refresh(expense)
        data = serialize_expense(expense)
        db.session.commit()

        return json_response(200, "花費更新成功。", data)

    @app.post("/api/invoices")
    def create_invoice():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = ("number", "issued_on", "amount", "kind")
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "發票號碼、開立日期、金額與種類為必填。", None)

        number = payload["number"]
        if not isinstance(number, str) or re.fullmatch(
            r"[A-Z]{2}[0-9]{8}",
            number,
        ) is None:
            return json_response(400, "發票號碼格式須為兩碼大寫英文加八碼數字。", None)

        kind = payload["kind"]
        if not isinstance(kind, str) or kind not in INVOICE_KINDS:
            return json_response(400, "發票種類不正確。", None)

        try:
            issued_on = parse_iso_date(payload["issued_on"], "開立日期")
            amount = parse_decimal(payload["amount"], "發票金額")
            if amount <= 0:
                raise ValueError("發票金額必須大於 0。")

            currency = payload.get("currency")
            if currency is None:
                currency = "TWD"
            else:
                currency = parse_currency(currency)

            fx_rate_to_twd = payload.get("fx_rate_to_twd")
            if fx_rate_to_twd is None:
                if currency != "TWD":
                    raise ValueError("外幣發票必須提供台幣匯率。")
                fx_rate_to_twd = Decimal("1")
            else:
                fx_rate_to_twd = parse_decimal(
                    fx_rate_to_twd,
                    "台幣匯率",
                )
            if fx_rate_to_twd <= 0:
                raise ValueError("台幣匯率必須大於 0。")

            random_code = payload.get("random_code")
            if random_code is not None and (
                not isinstance(random_code, str)
                or re.fullmatch(r"[0-9]{4}", random_code) is None
            ):
                raise ValueError("隨機碼必須是四碼數字。")

            seller_name = payload.get("seller_name")
            seller_ban = payload.get("seller_ban")
            if seller_name is not None and not isinstance(seller_name, str):
                raise ValueError("賣方名稱必須是文字或 null。")
            if seller_ban is not None and not isinstance(seller_ban, str):
                raise ValueError("賣方統一編號必須是文字或 null。")
        except ValueError as error:
            return json_response(400, str(error), None)

        if db.session.query(Invoice.id).filter(
            Invoice.number == number
        ).first():
            return json_response(400, "這個發票號碼已存在。", None)

        invoice = Invoice(
            number=number,
            issued_on=issued_on,
            amount=amount,
            kind=kind,
            currency=currency,
            fx_rate_to_twd=fx_rate_to_twd,
            random_code=random_code,
            seller_name=seller_name,
            seller_ban=seller_ban,
        )
        db.session.add(invoice)
        db.session.flush()
        db.session.refresh(invoice)
        data = serialize_invoice(invoice)
        db.session.commit()

        return json_response(201, "發票新增成功。", data)

    @app.get("/api/invoices")
    def list_invoices():
        filters = []
        period_key = request.args.get("period_key")
        if period_key is not None:
            try:
                start, end = period_date_range(period_key)
            except ValueError as error:
                return json_response(400, str(error), None)
            filters.extend(
                (Invoice.issued_on >= start, Invoice.issued_on <= end)
            )

        prize_status = request.args.get("prize_status")
        if prize_status is not None:
            if prize_status not in PRIZE_STATUSES:
                return json_response(400, "對獎狀態不正確。", None)
            filters.append(Invoice.prize_status == prize_status)

        invoices = Invoice.query.filter(*filters).order_by(Invoice.id).all()
        return json_response(
            200,
            "發票清單取得成功。",
            [serialize_invoice(invoice) for invoice in invoices],
        )

    @app.get("/api/invoices/<int:invoice_id>")
    def get_invoice(invoice_id):
        invoice = db.session.get(Invoice, invoice_id)
        if invoice is None:
            return json_response(404, "找不到這張發票。", None)

        data = serialize_invoice(invoice)
        items = InvoiceItem.query.filter_by(invoice_id=invoice_id).order_by(
            InvoiceItem.id
        ).all()
        expense_ids = (
            db.session.query(Expense.id)
            .filter(Expense.invoice_id == invoice_id)
            .order_by(Expense.id)
            .all()
        )
        data["items"] = [serialize_invoice_item(item) for item in items]
        data["expense_ids"] = [expense_id for (expense_id,) in expense_ids]
        return json_response(200, "發票資料取得成功。", data)

    @app.patch("/api/invoices/<int:invoice_id>")
    def update_invoice(invoice_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        invoice = db.session.get(Invoice, invoice_id)
        if invoice is None:
            return json_response(404, "找不到這張發票。", None)

        updates = {}
        for field in ("seller_name", "seller_ban"):
            if field not in payload or payload[field] is None:
                continue
            if not isinstance(payload[field], str):
                return json_response(400, "賣方欄位必須是文字或 null。", None)
            updates[field] = payload[field]

        if "random_code" in payload and payload["random_code"] is not None:
            random_code = payload["random_code"]
            if not isinstance(random_code, str) or re.fullmatch(
                r"[0-9]{4}",
                random_code,
            ) is None:
                return json_response(400, "隨機碼必須是四碼數字。", None)
            updates["random_code"] = random_code

        if "prize_status" in payload and payload["prize_status"] is not None:
            if payload["prize_status"] != "void":
                return json_response(400, "此處只能將發票標記為作廢。", None)
            updates["prize_status"] = "void"

        if not updates:
            return json_response(400, "請提供可更新的賣方、隨機碼或作廢狀態。", None)

        for field, value in updates.items():
            setattr(invoice, field, value)
        invoice.updated_at = func.now()

        db.session.flush()
        db.session.refresh(invoice)
        data = serialize_invoice(invoice)
        db.session.commit()

        return json_response(200, "發票更新成功。", data)

    @app.post("/api/invoices/<int:invoice_id>/items")
    def create_invoice_item(invoice_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = ("name", "quantity", "unit_price", "line_amount")
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "品名、數量、單價與小計為必填。", None)

        name = payload["name"]
        if not isinstance(name, str) or not name.strip():
            return json_response(400, "品名不可為空。", None)
        try:
            quantity = parse_decimal(payload["quantity"], "數量")
            unit_price = parse_decimal(payload["unit_price"], "單價")
            line_amount = parse_decimal(payload["line_amount"], "小計")
            if quantity <= 0 or unit_price <= 0 or line_amount <= 0:
                raise ValueError("數量、單價與小計都必須大於 0。")
        except ValueError as error:
            return json_response(400, str(error), None)

        if db.session.get(Invoice, invoice_id) is None:
            return json_response(400, "指定的發票不存在。", None)

        item = InvoiceItem(
            invoice_id=invoice_id,
            name=name.strip(),
            quantity=quantity,
            unit_price=unit_price,
            line_amount=line_amount,
        )
        db.session.add(item)
        db.session.flush()
        db.session.refresh(item)
        data = serialize_invoice_item(item)
        db.session.commit()

        return json_response(201, "發票品項新增成功。", data)

    @app.get("/api/invoices/<int:invoice_id>/items")
    def list_invoice_items(invoice_id):
        if db.session.get(Invoice, invoice_id) is None:
            return json_response(404, "找不到這張發票。", None)

        items = InvoiceItem.query.filter_by(invoice_id=invoice_id).order_by(
            InvoiceItem.id
        ).all()
        return json_response(
            200,
            "發票品項清單取得成功。",
            [serialize_invoice_item(item) for item in items],
        )

    @app.post("/api/draw-periods")
    def create_draw_period():
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        period_key = payload.get("period_key")
        try:
            period_date_range(period_key)
        except ValueError as error:
            return json_response(400, str(error), None)

        if db.session.query(DrawPeriod.id).filter(
            DrawPeriod.period_key == period_key
        ).first():
            return json_response(400, "這個開獎期別已存在。", None)

        period = DrawPeriod(period_key=period_key)
        db.session.add(period)
        db.session.flush()
        data = {"id": period.id, "period_key": period.period_key}
        db.session.commit()

        return json_response(201, "開獎期別新增成功。", data)

    @app.post("/api/draw-periods/<int:period_id>/prizes")
    def create_draw_prize(period_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        required_fields = ("tier", "matching_number", "amount")
        if any(
            field not in payload or payload[field] is None
            for field in required_fields
        ):
            return json_response(400, "獎項、獎號與獎金為必填。", None)

        tier = payload["tier"]
        if not isinstance(tier, str) or tier not in DRAW_PRIZE_TIERS:
            return json_response(400, "獎項類別不正確。", None)

        matching_number = payload["matching_number"]
        if (
            not isinstance(matching_number, str)
            or re.fullmatch(r"[0-9]{1,8}", matching_number) is None
        ):
            return json_response(400, "獎號必須是一至八碼數字。", None)
        if tier in FULL_NUMBER_TIERS and len(matching_number) != 8:
            return json_response(400, "特別獎、特獎與頭獎須使用八碼獎號。", None)

        try:
            amount = parse_decimal(payload["amount"], "獎金")
            if amount < 0:
                raise ValueError("獎金不可小於 0。")
        except ValueError as error:
            return json_response(400, str(error), None)

        period = db.session.get(DrawPeriod, period_id)
        if period is None:
            return json_response(400, "指定的開獎期別不存在。", None)

        if db.session.query(DrawPrize.id).filter(
            DrawPrize.draw_period_id == period_id,
            DrawPrize.tier == tier,
            DrawPrize.matching_number == matching_number,
        ).first():
            return json_response(400, "這組獎號已存在於該期別。", None)

        prize = DrawPrize(
            draw_period_id=period_id,
            tier=tier,
            matching_number=matching_number,
            amount=amount,
        )
        db.session.add(prize)
        db.session.flush()
        db.session.refresh(prize)
        data = serialize_draw_prize(prize)
        db.session.commit()

        return json_response(201, "獎號新增成功。", data)

    @app.post("/api/draw-periods/<int:period_id>/check")
    def check_draw_period(period_id):
        period = (
            DrawPeriod.query.filter_by(id=period_id)
            .with_for_update()
            .first()
        )
        if period is None:
            return json_response(400, "指定的開獎期別不存在。", None)

        try:
            start, end = period_date_range(period.period_key)
        except ValueError as error:
            return json_response(400, str(error), None)

        prizes = DrawPrize.query.filter_by(
            draw_period_id=period_id
        ).order_by(DrawPrize.id).all()
        invoices = (
            Invoice.query.filter(
                Invoice.issued_on >= start,
                Invoice.issued_on <= end,
                Invoice.prize_status != "void",
            )
            .order_by(Invoice.id)
            .with_for_update()
            .all()
        )

        won_count = 0
        for invoice in invoices:
            prize = find_matching_prize(invoice.number, prizes)
            invoice.prize_status = "won" if prize is not None else "lost"
            invoice.updated_at = func.now()
            if prize is not None:
                won_count += 1

        db.session.commit()
        return json_response(
            200,
            "本期發票對獎完成。",
            {
                "checked_count": len(invoices),
                "won_count": won_count,
            },
        )

    @app.post("/api/invoices/<int:invoice_id>/prize-income")
    def create_invoice_prize_income(invoice_id):
        payload = request_json_object()
        if payload is None:
            return json_response(400, "請提供有效的 JSON 物件。", None)

        category_id = payload.get("category_id")
        account_id = payload.get("account_id")
        if type(category_id) is not int or type(account_id) is not int:
            return json_response(400, "入帳分類與帳戶編號為必填整數。", None)

        invoice = (
            Invoice.query.filter_by(id=invoice_id)
            .with_for_update()
            .first()
        )
        if invoice is None:
            return json_response(404, "找不到這張發票。", None)

        existing_income = db.session.query(Income.id).filter(
            Income.invoice_id == invoice_id
        ).first()
        if existing_income:
            return json_response(400, "這張發票已建立中獎入帳。", None)
        if invoice.prize_status != "won":
            return json_response(400, "只有已確認中獎的發票可以建立入帳。", None)

        period_key = invoice_period_key(invoice.issued_on)
        period = DrawPeriod.query.filter_by(period_key=period_key).first()
        if period is None:
            return json_response(400, "這張發票所屬期別尚未建立。", None)
        prizes = DrawPrize.query.filter_by(
            draw_period_id=period.id
        ).order_by(DrawPrize.id).all()
        prize = find_matching_prize(invoice.number, prizes)
        if prize is None:
            return json_response(400, "找不到這張發票對應的獎金資料。", None)
        if prize.amount <= 0:
            return json_response(400, "中獎獎金必須大於 0 才能建立入帳。", None)

        category = db.session.get(IncomeCategory, category_id)
        account = db.session.get(Account, account_id)
        if category is None:
            return json_response(400, "指定的入帳分類不存在。", None)
        if account is None:
            return json_response(400, "指定的帳戶不存在。", None)
        if account.currency != invoice.currency:
            return json_response(400, "入帳幣別必須與帳戶幣別相同。", None)

        income = Income(
            received_on=datetime.now(timezone.utc).date(),
            amount=prize.amount,
            currency=invoice.currency,
            fx_rate_to_twd=invoice.fx_rate_to_twd,
            category_id=category_id,
            account_id=account_id,
            source="統一發票中獎",
            invoice_id=invoice.id,
        )
        invoice.prize_status = "claimed"
        invoice.updated_at = func.now()
        db.session.add(income)
        db.session.flush()
        db.session.refresh(invoice)
        db.session.refresh(income)
        data = {
            "invoice": serialize_invoice(invoice),
            "income": serialize_income(income),
        }
        db.session.commit()

        return json_response(201, "中獎入帳新增成功。", data)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
