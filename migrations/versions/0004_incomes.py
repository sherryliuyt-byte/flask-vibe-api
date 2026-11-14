"""Create income categories and incomes tables.

Revision ID: 0004_incomes
Revises: 0003_invoices_draws
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_incomes"
down_revision: Union[str, None] = "0003_invoices_draws"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "income_categories",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_income_categories"),
        sa.UniqueConstraint("name", name="uq_income_categories_name"),
    )
    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fx_rate_to_twd", sa.Numeric(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
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
            name="ck_incomes_amount_positive",
        ),
        sa.CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_incomes_fx_rate_to_twd_positive",
        ),
        sa.CheckConstraint(
            "NULLIF(BTRIM(source), '') IS NOT NULL "
            "OR NULLIF(BTRIM(note), '') IS NOT NULL",
            name="ck_incomes_source_or_note_present",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_incomes_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["income_categories.id"],
            name="fk_incomes_category_id_income_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_incomes_invoice_id_invoices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incomes"),
        sa.UniqueConstraint("invoice_id", name="uq_incomes_invoice_id"),
    )


def downgrade() -> None:
    op.drop_table("incomes")
    op.drop_table("income_categories")
