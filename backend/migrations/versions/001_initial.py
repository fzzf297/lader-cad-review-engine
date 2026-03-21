"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建枚举类型
    file_status_enum = sa.Enum(
        'uploading', 'uploaded', 'processing', 'reviewed', 'error',
        name='filestatus',
        create_type=False
    )
    severity_level_enum = sa.Enum(
        'error', 'warning', 'info',
        name='severitylevel',
        create_type=False
    )
    issue_source_enum = sa.Enum(
        'rule', 'llm', 'both',
        name='issuesource',
        create_type=False
    )

    # 显式创建枚举类型（PostgreSQL）
    op.execute("CREATE TYPE filestatus AS ENUM ('uploading', 'uploaded', 'processing', 'reviewed', 'error')")
    op.execute("CREATE TYPE severitylevel AS ENUM ('error', 'warning', 'info')")
    op.execute("CREATE TYPE issuesource AS ENUM ('rule', 'llm', 'both')")

    # 创建 dwg_files 表
    op.create_table(
        'dwg_files',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('upload_time', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('status', file_status_enum, nullable=False, server_default='uploaded'),
    )

    # 创建 contract_files 表
    op.create_table(
        'contract_files',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('upload_time', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # 创建 review_records 表
    op.create_table(
        'review_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dwg_file_id', sa.String(36), sa.ForeignKey('dwg_files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contract_file_id', sa.String(36), sa.ForeignKey('contract_files.id', ondelete='SET NULL'), nullable=True),
        sa.Column('review_time', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('overall_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('assessment', sa.String(50), nullable=False, server_default=''),
        sa.Column('result_json', sa.Text(), nullable=False, server_default='{}'),
    )

    # 创建 review_records 索引
    op.create_index('ix_review_records_dwg_file_id', 'review_records', ['dwg_file_id'])
    op.create_index('ix_review_records_contract_file_id', 'review_records', ['contract_file_id'])
    op.create_index('ix_review_records_review_time', 'review_records', ['review_time'])

    # 创建 review_issues 表
    op.create_table(
        'review_issues',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_id', sa.String(36), sa.ForeignKey('review_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('severity', severity_level_enum, nullable=False, server_default='warning'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('location', sa.String(255), nullable=False, server_default=''),
        sa.Column('suggestion', sa.Text(), nullable=False, server_default=''),
        sa.Column('source', issue_source_enum, nullable=False, server_default='rule'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
    )

    # 创建 review_issues 索引
    op.create_index('ix_review_issues_review_id', 'review_issues', ['review_id'])
    op.create_index('ix_review_issues_category', 'review_issues', ['category'])
    op.create_index('ix_review_issues_severity', 'review_issues', ['severity'])


def downgrade() -> None:
    # 删除 review_issues 表
    op.drop_index('ix_review_issues_severity', table_name='review_issues')
    op.drop_index('ix_review_issues_category', table_name='review_issues')
    op.drop_index('ix_review_issues_review_id', table_name='review_issues')
    op.drop_table('review_issues')

    # 删除 review_records 表
    op.drop_index('ix_review_records_review_time', table_name='review_records')
    op.drop_index('ix_review_records_contract_file_id', table_name='review_records')
    op.drop_index('ix_review_records_dwg_file_id', table_name='review_records')
    op.drop_table('review_records')

    # 删除 contract_files 表
    op.drop_table('contract_files')

    # 删除 dwg_files 表
    op.drop_table('dwg_files')

    # 删除枚举类型
    op.execute("DROP TYPE IF EXISTS issuesource")
    op.execute("DROP TYPE IF EXISTS severitylevel")
    op.execute("DROP TYPE IF EXISTS filestatus")