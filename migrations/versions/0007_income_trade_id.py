"""Add trade reference to incomes.

Revision ID: 0007_income_trade_id
Revises: 0006_instruments_trades
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_income_trade_id"
down_revision: Union[str, None] = "0006_instruments_trades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incomes",
        sa.Column("trade_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_incomes_trade_id_trades",
        "incomes",
        "trades",
        ["trade_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_incomes_trade_id",
        "incomes",
        ["trade_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_incomes_trade_id", "incomes", type_="unique")
    op.drop_constraint("fk_incomes_trade_id_trades", "incomes", type_="foreignkey")
    op.drop_column("incomes", "trade_id")
