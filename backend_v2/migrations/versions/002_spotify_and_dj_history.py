"""add_spotify_context_and_dj_history

Revision ID: 002_spotify_and_dj_history
Revises: 001_track_intents
Create Date: 2025-01-01 12:00:00.000000

This migration adds:
1. SpotifyUserContext table for storing Spotify OAuth tokens and enriched listening data
2. DJSpeechHistory table for tracking DJ speech for continuity
3. spotify_connected_at column to users table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_spotify_and_dj_history'
down_revision: Union[str, None] = '001_track_intents'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add spotify_connected_at column to users table
    op.add_column('users', sa.Column('spotify_connected_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create spotify_user_context table
    op.create_table(
        'spotify_user_context',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('spotify_id', sa.String(255), nullable=False),
        sa.Column('top_artists_json', sa.Text(), nullable=True),
        sa.Column('top_tracks_json', sa.Text(), nullable=True),
        sa.Column('recently_played_json', sa.Text(), nullable=True),
        sa.Column('playlists_json', sa.Text(), nullable=True),
        sa.Column('music_preferences_json', sa.Text(), nullable=True),
        sa.Column('listening_habits_json', sa.Text(), nullable=True),
        sa.Column('genres_analysis_json', sa.Text(), nullable=True),
        sa.Column('mood_analysis_json', sa.Text(), nullable=True),
        sa.Column('favorite_tracks_with_stats_json', sa.Text(), nullable=True),
        sa.Column('access_token', sa.String(512), nullable=False),
        sa.Column('refresh_token', sa.String(512), nullable=False),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id'),
    )
    
    # Create indexes for spotify_user_context
    op.create_index('ix_spotify_user_context_user_id', 'spotify_user_context', ['user_id'])
    op.create_index('ix_spotify_user_context_spotify_id', 'spotify_user_context', ['spotify_id'])
    
    # Create dj_speech_history table
    op.create_table(
        'dj_speech_history',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('speech_text', sa.Text(), nullable=False),
        sa.Column('mentioned_artists', sa.Text(), nullable=True),
        sa.Column('mentioned_tracks', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for dj_speech_history
    op.create_index('ix_dj_speech_history_user_id', 'dj_speech_history', ['user_id'])
    op.create_index('ix_dj_speech_history_session_id', 'dj_speech_history', ['session_id'])
    op.create_index('ix_dj_speech_history_created_at', 'dj_speech_history', ['created_at'])
    op.create_index('ix_dj_speech_history_user_session', 'dj_speech_history', ['user_id', 'session_id'])


def downgrade() -> None:
    # Drop dj_speech_history table
    op.drop_index('ix_dj_speech_history_user_session', table_name='dj_speech_history')
    op.drop_index('ix_dj_speech_history_created_at', table_name='dj_speech_history')
    op.drop_index('ix_dj_speech_history_session_id', table_name='dj_speech_history')
    op.drop_index('ix_dj_speech_history_user_id', table_name='dj_speech_history')
    op.drop_table('dj_speech_history')
    
    # Drop spotify_user_context table
    op.drop_index('ix_spotify_user_context_spotify_id', table_name='spotify_user_context')
    op.drop_index('ix_spotify_user_context_user_id', table_name='spotify_user_context')
    op.drop_table('spotify_user_context')
    
    # Remove spotify_connected_at column from users table
    op.drop_column('users', 'spotify_connected_at')

