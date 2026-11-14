from sqlalchemy import CheckConstraint, ForeignKey, Identity, func, text

from extensions import db


class Account(db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        db.UniqueConstraint("name", name="uq_accounts_name"),
        CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="ck_accounts_kind",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_accounts_currency_format",
        ),
        CheckConstraint(
            "statement_day IS NULL OR statement_day BETWEEN 1 AND 31",
            name="ck_accounts_statement_day",
        ),
        CheckConstraint(
            "payment_day IS NULL OR payment_day BETWEEN 1 AND 31",
            name="ck_accounts_payment_day",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        server_default=text("'TWD'"),
    )
    opening_balance = db.Column(
        db.Numeric(),
        nullable=False,
        server_default=text("0"),
    )
    statement_day = db.Column(db.Integer)
    payment_day = db.Column(db.Integer)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )


class Transfer(db.Model):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_transfers_fx_rate_to_twd_positive",
        ),
        CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_distinct_accounts",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_transfers_currency_format",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    transferred_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(db.Numeric(), nullable=False)
    from_account_id = db.Column(
        db.Integer,
        ForeignKey(
            "accounts.id",
            name="fk_transfers_from_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    to_account_id = db.Column(
        db.Integer,
        ForeignKey(
            "accounts.id",
            name="fk_transfers_to_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )


class Invoice(db.Model):
    __tablename__ = "invoices"
    __table_args__ = (
        db.UniqueConstraint("number", name="uq_invoices_number"),
        CheckConstraint(
            "number ~ '^[A-Z]{2}[0-9]{8}$'",
            name="ck_invoices_number_format",
        ),
        CheckConstraint("amount > 0", name="ck_invoices_amount_positive"),
        CheckConstraint(
            "kind IN ('paper', 'electronic')",
            name="ck_invoices_kind",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_invoices_fx_rate_to_twd_positive",
        ),
        CheckConstraint(
            "random_code IS NULL OR random_code ~ '^[0-9]{4}$'",
            name="ck_invoices_random_code_format",
        ),
        CheckConstraint(
            "prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')",
            name="ck_invoices_prize_status",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    number = db.Column(db.String(10), nullable=False)
    issued_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        server_default=text("'TWD'"),
    )
    fx_rate_to_twd = db.Column(db.Numeric(), nullable=False)
    random_code = db.Column(db.String(4))
    seller_name = db.Column(db.String())
    seller_ban = db.Column(db.String())
    prize_status = db.Column(
        db.String(16),
        nullable=False,
        server_default=text("'unchecked'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_invoice_items_quantity_positive",
        ),
        CheckConstraint(
            "unit_price > 0",
            name="ck_invoice_items_unit_price_positive",
        ),
        CheckConstraint(
            "line_amount > 0",
            name="ck_invoice_items_line_amount_positive",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    invoice_id = db.Column(
        db.Integer,
        ForeignKey(
            "invoices.id",
            name="fk_invoice_items_invoice_id_invoices",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    name = db.Column(db.String(), nullable=False)
    quantity = db.Column(db.Numeric(), nullable=False)
    unit_price = db.Column(db.Numeric(), nullable=False)
    line_amount = db.Column(db.Numeric(), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )


class DrawPeriod(db.Model):
    __tablename__ = "draw_periods"
    __table_args__ = (
        db.UniqueConstraint("period_key", name="uq_draw_periods_period_key"),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    period_key = db.Column(db.String(), nullable=False)


class DrawPrize(db.Model):
    __tablename__ = "draw_prizes"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', "
            "'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name="ck_draw_prizes_tier",
        ),
        CheckConstraint(
            "amount >= 0",
            name="ck_draw_prizes_amount_nonnegative",
        ),
        db.UniqueConstraint(
            "draw_period_id",
            "tier",
            "matching_number",
            name="uq_draw_prizes_period_tier_number",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    draw_period_id = db.Column(
        db.Integer,
        ForeignKey(
            "draw_periods.id",
            name="fk_draw_prizes_draw_period_id_draw_periods",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tier = db.Column(db.String(20), nullable=False)
    matching_number = db.Column(db.String(), nullable=False)
    amount = db.Column(db.Numeric(), nullable=False)
