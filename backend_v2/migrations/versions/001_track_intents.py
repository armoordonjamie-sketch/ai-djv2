"""add_track_intents_and_mood_enhancements

Revision ID: 001_track_intents
Revises: 
Create Date: 2025-01-01 00:00:00.000000

This migration adds:
1. TrackIntent and AcquisitionJob tables for decoupled track selection
2. Enhanced mood columns for genre seeds, vibe keywords, example artists, etc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_track_intents'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create track_intents table
    op.create_table(
        'track_intents',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('mood_id', sa.String(36), nullable=True),
        sa.Column('session_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('artist', sa.String(255), nullable=False),
        sa.Column('album', sa.String(255), nullable=True),
        sa.Column('spotify_id', sa.String(50), nullable=True),
        sa.Column('apple_music_id', sa.String(50), nullable=True),
        sa.Column('isrc', sa.String(20), nullable=True),
        sa.Column('target_energy', sa.Float(), nullable=True),
        sa.Column('target_valence', sa.Float(), nullable=True),
        sa.Column('target_tempo', sa.Float(), nullable=True),
        sa.Column('target_danceability', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('acquired_song_uuid', sa.String(36), nullable=True),
        sa.Column('selection_rationale', sa.Text(), nullable=True),
        sa.Column('selection_method', sa.String(50), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mood_id'], ['moods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['acquired_song_uuid'], ['songs.uuid'], ondelete='SET NULL'),
    )
    
    # Create indexes for track_intents
    op.create_index('ix_track_intents_user_id', 'track_intents', ['user_id'])
    op.create_index('ix_track_intents_mood_id', 'track_intents', ['mood_id'])
    op.create_index('ix_track_intents_session_id', 'track_intents', ['session_id'])
    op.create_index('ix_track_intents_status', 'track_intents', ['status'])
    op.create_index('ix_track_intents_spotify_id', 'track_intents', ['spotify_id'])
    op.create_index('ix_track_intents_apple_music_id', 'track_intents', ['apple_music_id'])
    op.create_index('ix_track_intents_isrc', 'track_intents', ['isrc'])
    op.create_index('ix_track_intents_user_status', 'track_intents', ['user_id', 'status'])
    op.create_index('ix_track_intents_session_status', 'track_intents', ['session_id', 'status'])
    
    # Create acquisition_jobs table
    op.create_table(
        'acquisition_jobs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('track_intent_id', sa.String(36), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('query', sa.Text(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('acquired_path', sa.String(500), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='QUEUED'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['track_intent_id'], ['track_intents.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for acquisition_jobs
    op.create_index('ix_acquisition_jobs_track_intent_id', 'acquisition_jobs', ['track_intent_id'])
    op.create_index('ix_acquisition_jobs_provider', 'acquisition_jobs', ['provider'])
    op.create_index('ix_acquisition_jobs_status', 'acquisition_jobs', ['status'])
    op.create_index('ix_acquisition_jobs_status_created', 'acquisition_jobs', ['status', 'created_at'])
    
    # Add new columns to moods table
    op.add_column('moods', sa.Column('danceability_target', sa.Float(), nullable=True))
    op.add_column('moods', sa.Column('tempo_min', sa.Integer(), nullable=True))
    op.add_column('moods', sa.Column('tempo_max', sa.Integer(), nullable=True))
    op.add_column('moods', sa.Column('genre_seeds_json', sa.Text(), nullable=True))
    op.add_column('moods', sa.Column('vibe_keywords_json', sa.Text(), nullable=True))
    op.add_column('moods', sa.Column('avoid_genres_json', sa.Text(), nullable=True))
    op.add_column('moods', sa.Column('example_artists_json', sa.Text(), nullable=True))
    op.add_column('moods', sa.Column('intro_personality', sa.String(100), nullable=True))
    op.add_column('moods', sa.Column('era_hint', sa.String(50), nullable=True))


def downgrade() -> None:
    # Remove mood columns
    op.drop_column('moods', 'era_hint')
    op.drop_column('moods', 'intro_personality')
    op.drop_column('moods', 'example_artists_json')
    op.drop_column('moods', 'avoid_genres_json')
    op.drop_column('moods', 'vibe_keywords_json')
    op.drop_column('moods', 'genre_seeds_json')
    op.drop_column('moods', 'tempo_max')
    op.drop_column('moods', 'tempo_min')
    op.drop_column('moods', 'danceability_target')
    
    # Drop acquisition_jobs table
    op.drop_index('ix_acquisition_jobs_status_created', table_name='acquisition_jobs')
    op.drop_index('ix_acquisition_jobs_status', table_name='acquisition_jobs')
    op.drop_index('ix_acquisition_jobs_provider', table_name='acquisition_jobs')
    op.drop_index('ix_acquisition_jobs_track_intent_id', table_name='acquisition_jobs')
    op.drop_table('acquisition_jobs')
    
    # Drop track_intents table
    op.drop_index('ix_track_intents_session_status', table_name='track_intents')
    op.drop_index('ix_track_intents_user_status', table_name='track_intents')
    op.drop_index('ix_track_intents_isrc', table_name='track_intents')
    op.drop_index('ix_track_intents_apple_music_id', table_name='track_intents')
    op.drop_index('ix_track_intents_spotify_id', table_name='track_intents')
    op.drop_index('ix_track_intents_status', table_name='track_intents')
    op.drop_index('ix_track_intents_session_id', table_name='track_intents')
    op.drop_index('ix_track_intents_mood_id', table_name='track_intents')
    op.drop_index('ix_track_intents_user_id', table_name='track_intents')
    op.drop_table('track_intents')

