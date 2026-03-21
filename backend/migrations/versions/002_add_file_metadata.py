"""Add file metadata and review llm flag

Revision ID: 002
Revises: 001
Create Date: 2026-03-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dwg_files', sa.Column('original_path', sa.String(length=512), nullable=True))
    op.add_column('dwg_files', sa.Column('suffix', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('dwg_files', sa.Column('converted', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column('contract_files', sa.Column('original_path', sa.String(length=512), nullable=True))
    op.add_column('contract_files', sa.Column('suffix', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('contract_files', sa.Column('converted', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column('review_records', sa.Column('enable_llm', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('review_records', 'enable_llm')

    op.drop_column('contract_files', 'converted')
    op.drop_column('contract_files', 'suffix')
    op.drop_column('contract_files', 'original_path')

    op.drop_column('dwg_files', 'converted')
    op.drop_column('dwg_files', 'suffix')
    op.drop_column('dwg_files', 'original_path')
