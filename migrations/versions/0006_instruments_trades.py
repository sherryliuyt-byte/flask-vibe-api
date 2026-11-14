"""Create instruments and trades tables.

Revision ID: 0006_instruments_trades
Revises: 0005_expenses
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_instruments_trades"
down_revision: Union[str, None] = "0005_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "market IN ('tw_stock', 'us_stock', 'fund', 'other')",
            name="ck_instruments_market",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_instruments"),
        sa.UniqueConstraint(
            "market",
            "symbol",
            name="uq_instruments_market_symbol",
        ),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("trade_type", sa.String(length=24), nullable=False),
        sa.Column("traded_on", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("cash_amount", sa.Numeric(), nullable=True),
        sa.Column("ratio", sa.Numeric(), nullable=True),
        sa.Column("fee", sa.Numeric(), nullable=True),
        sa.Column("tax", sa.Numeric(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fx_rate_to_twd", sa.Numeric(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "trade_type IN ('buy', 'sell', 'cash_dividend', "
            "'stock_dividend', 'drip', 'split', 'merge', "
            "'capital_reduction')",
            name="ck_trades_trade_type",
        ),
        sa.CheckConstraint(
            "fee IS NULL OR fee >= 0",
            name="ck_trades_fee_nonnegative",
        ),
        sa.CheckConstraint(
            "tax IS NULL OR tax >= 0",
            name="ck_trades_tax_nonnegative",
        ),
        sa.CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_trades_fx_rate_to_twd_positive",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_trades_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name="fk_trades_instrument_id_instruments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trades"),
    )


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("instruments")
