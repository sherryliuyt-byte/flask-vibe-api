import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import jsonify, request


CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")
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


def parse_iso_datetime(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name}必須是含時區的 ISO 日期時間。")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name}格式不正確。") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}必須包含時區。")
    return parsed


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
        "trade_id": income.trade_id,
        "created_at": income.created_at.isoformat(),
        "updated_at": income.updated_at.isoformat(),
    }


def serialize_instrument(instrument):
    return {
        "id": instrument.id,
        "market": instrument.market,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "currency": instrument.currency,
        "created_at": instrument.created_at.isoformat(),
        "updated_at": instrument.updated_at.isoformat(),
    }


def serialize_trade(trade):
    return {
        "id": trade.id,
        "instrument_id": trade.instrument_id,
        "account_id": trade.account_id,
        "trade_type": trade.trade_type,
        "traded_on": trade.traded_on.isoformat(),
        "quantity": str(trade.quantity) if trade.quantity is not None else None,
        "price": str(trade.price) if trade.price is not None else None,
        "cash_amount": (
            str(trade.cash_amount) if trade.cash_amount is not None else None
        ),
        "ratio": str(trade.ratio) if trade.ratio is not None else None,
        "fee": str(trade.fee) if trade.fee is not None else None,
        "tax": str(trade.tax) if trade.tax is not None else None,
        "currency": trade.currency,
        "fx_rate_to_twd": str(trade.fx_rate_to_twd),
        "voided_at": (
            trade.voided_at.isoformat() if trade.voided_at is not None else None
        ),
        "created_at": trade.created_at.isoformat(),
        "updated_at": trade.updated_at.isoformat(),
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
