"""Add training_metrics table

Revision ID: 004
Revises: 003
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import DateTime

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'training_metrics',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('mood_id', sa.String(36), sa.ForeignKey('moods.id', ondelete='CASCADE')),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('agent_name', sa.String(50)),
        sa.Column('feedback_type', sa.String(20)),
        sa.Column('track_artist', sa.String(255)),
        sa.Column('track_title', sa.String(255)),
        sa.Column('artists_before', sa.Text),
        sa.Column('artists_after', sa.Text),
        sa.Column('artists_added', sa.Integer, default=0),
        sa.Column('artists_removed', sa.Integer, default=0),
        sa.Column('artists_demoted', sa.Integer, default=0),
        sa.Column('llm_reasoning', sa.Text),
        sa.Column('tool_calls_made', sa.Integer, default=0),
        sa.Column('llm_tokens', sa.Integer, default=0),
        sa.Column('subsequent_likes', sa.Integer, default=0),
        sa.Column('subsequent_dislikes', sa.Integer, default=0),
        sa.Column('effectiveness_score', sa.Float),
        sa.Column('created_at', DateTime(timezone=True)),
    )
    
    op.create_index('ix_training_metrics_mood', 'training_metrics', ['mood_id'])
    op.create_index('ix_training_metrics_user', 'training_metrics', ['user_id'])
    op.create_index('ix_training_metrics_created', 'training_metrics', ['created_at'])


def downgrade():
    op.drop_index('ix_training_metrics_created', table_name='training_metrics')
    op.drop_index('ix_training_metrics_user', table_name='training_metrics')
    op.drop_index('ix_training_metrics_mood', table_name='training_metrics')
    op.drop_table('training_metrics')

