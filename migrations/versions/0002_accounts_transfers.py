"""Create accounts and transfers tables.

Revision ID: 0002_accounts_transfers
Revises: 0001_initial
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_accounts_transfers"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'TWD'"),
            nullable=False,
        ),
        sa.Column(
            "opening_balance",
            sa.Numeric(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("statement_day", sa.Integer(), nullable=True),
        sa.Column("payment_day", sa.Integer(), nullable=True),
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
            "currency ~ '^[A-Z]{3}$'",
            name="ck_accounts_currency_format",
        ),
        sa.CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="ck_accounts_kind",
        ),
        sa.CheckConstraint(
            "payment_day IS NULL OR payment_day BETWEEN 1 AND 31",
            name="ck_accounts_payment_day",
        ),
        sa.CheckConstraint(
            "statement_day IS NULL OR statement_day BETWEEN 1 AND 31",
            name="ck_accounts_statement_day",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("name", name="uq_accounts_name"),
    )
    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("transferred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fx_rate_to_twd", sa.Numeric(), nullable=False),
        sa.Column("from_account_id", sa.Integer(), nullable=False),
        sa.Column("to_account_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
            "amount > 0",
            name="ck_transfers_amount_positive",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_transfers_currency_format",
        ),
        sa.CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_distinct_accounts",
        ),
        sa.CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_transfers_fx_rate_to_twd_positive",
        ),
        sa.ForeignKeyConstraint(
            ["from_account_id"],
            ["accounts.id"],
            name="fk_transfers_from_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_account_id"],
            ["accounts.id"],
            name="fk_transfers_to_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transfers"),
    )


def downgrade() -> None:
    op.drop_table("transfers")
    op.drop_table("accounts")
