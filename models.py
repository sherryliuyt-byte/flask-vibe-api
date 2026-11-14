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
