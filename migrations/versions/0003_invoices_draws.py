"""Create invoice and draw tables.

Revision ID: 0003_invoices_draws
Revises: 0002_accounts_transfers
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_invoices_draws"
down_revision: Union[str, None] = "0002_accounts_transfers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("number", sa.String(length=10), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'TWD'"),
            nullable=False,
        ),
        sa.Column("fx_rate_to_twd", sa.Numeric(), nullable=False),
        sa.Column("random_code", sa.String(length=4), nullable=True),
        sa.Column("seller_name", sa.String(), nullable=True),
        sa.Column("seller_ban", sa.String(), nullable=True),
        sa.Column(
            "prize_status",
            sa.String(length=16),
            server_default=sa.text("'unchecked'"),
            nullable=False,
        ),
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
            name="ck_invoices_amount_positive",
        ),
        sa.CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_invoices_fx_rate_to_twd_positive",
        ),
        sa.CheckConstraint(
            "kind IN ('paper', 'electronic')",
            name="ck_invoices_kind",
        ),
        sa.CheckConstraint(
            "number ~ '^[A-Z]{2}[0-9]{8}$'",
            name="ck_invoices_number_format",
        ),
        sa.CheckConstraint(
            "prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')",
            name="ck_invoices_prize_status",
        ),
        sa.CheckConstraint(
            "random_code IS NULL OR random_code ~ '^[0-9]{4}$'",
            name="ck_invoices_random_code_format",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("number", name="uq_invoices_number"),
    )
    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("line_amount", sa.Numeric(), nullable=False),
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
            "line_amount > 0",
            name="ck_invoice_items_line_amount_positive",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_invoice_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price > 0",
            name="ck_invoice_items_unit_price_positive",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_invoice_items_invoice_id_invoices",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_items"),
    )
    op.create_table(
        "draw_periods",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("period_key", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_draw_periods"),
        sa.UniqueConstraint("period_key", name="uq_draw_periods_period_key"),
    )
    op.create_table(
        "draw_prizes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("draw_period_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("matching_number", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_draw_prizes_amount_nonnegative",
        ),
        sa.CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', "
            "'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name="ck_draw_prizes_tier",
        ),
        sa.ForeignKeyConstraint(
            ["draw_period_id"],
            ["draw_periods.id"],
            name="fk_draw_prizes_draw_period_id_draw_periods",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_draw_prizes"),
        sa.UniqueConstraint(
            "draw_period_id",
            "tier",
            "matching_number",
            name="uq_draw_prizes_period_tier_number",
        ),
    )


def downgrade() -> None:
    op.drop_table("draw_prizes")
    op.drop_table("draw_periods")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
