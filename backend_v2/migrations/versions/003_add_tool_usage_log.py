"""add_tool_usage_log_table

Revision ID: 003
Revises: 002
Create Date: 2024-12-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002_spotify_and_dj_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Create tool_usage_log table
    op.create_table(
        'tool_usage_log',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('mood_id', sa.String(length=36), nullable=True),
        sa.Column('llm_trace_id', sa.Integer(), nullable=True),
        sa.Column('agent_name', sa.String(length=50), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_arguments', sa.Text(), nullable=True),
        sa.Column('tool_result', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Float(), nullable=True),
        sa.Column('success', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['llm_trace_id'], ['llm_trace.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['mood_id'], ['moods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_tool_usage_log_session_id'), 'tool_usage_log', ['session_id'], unique=False)
    op.create_index(op.f('ix_tool_usage_log_user_id'), 'tool_usage_log', ['user_id'], unique=False)
    op.create_index(op.f('ix_tool_usage_log_llm_trace_id'), 'tool_usage_log', ['llm_trace_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_tool_usage_log_llm_trace_id'), table_name='tool_usage_log')
    op.drop_index(op.f('ix_tool_usage_log_user_id'), table_name='tool_usage_log')
    op.drop_index(op.f('ix_tool_usage_log_session_id'), table_name='tool_usage_log')
    
    # Drop table
    op.drop_table('tool_usage_log')


