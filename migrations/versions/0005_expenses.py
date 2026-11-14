"""Create expense categories and expenses tables.

Revision ID: 0005_expenses
Revises: 0004_incomes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_expenses"
down_revision: Union[str, None] = "0004_incomes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_expense_categories"),
        sa.UniqueConstraint("name", name="uq_expense_categories_name"),
    )
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fx_rate_to_twd", sa.Numeric(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("settled_on", sa.Date(), nullable=True),
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
            name="ck_expenses_amount_positive",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_expenses_currency_format",
        ),
        sa.CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_expenses_fx_rate_to_twd_positive",
        ),
        sa.CheckConstraint(
            "NULLIF(BTRIM(merchant), '') IS NOT NULL "
            "OR NULLIF(BTRIM(note), '') IS NOT NULL",
            name="ck_expenses_merchant_or_note_present",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_expenses_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["expense_categories.id"],
            name="fk_expenses_category_id_expense_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_expenses_invoice_id_invoices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
    )


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("expense_categories")
