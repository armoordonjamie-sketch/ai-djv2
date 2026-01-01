"""
Database Tools for AI Agents

Provides tool definitions and implementations for AI agents to interface
with the database directly for song selection, history analysis, and user preferences.

These tools follow the OpenRouter tool calling specification.
"""

import logging
import json
import inspect
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend_v2.models.existing import (
    Song,
    PlayHistory,
    SongFeatures,
    LyricsAnalysis,
    Session,
)
from backend_v2.models.user import User
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.spotify_context import SpotifyUserContext as SpotifyContext
from backend_v2.models.mood import Mood, MoodProfile
from backend_v2.models.track_intent import TrackIntent
from backend_v2.models.feedback import FeedbackEvent

logger = logging.getLogger("ai-dj.db-tools")


def _is_uuid(value: Optional[str]) -> bool:
    """Return True if value looks like a UUID string."""
    if value is None:
        return False
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _get_spotify_oauth_client() -> Optional["SpotifyOAuth"]:
    """Build a Spotify OAuth client from environment variables."""
    import os
    from backend_v2.integrations.spotify import SpotifyOAuth

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/spotify/callback")

    if not client_id:
        logger.warning("Spotify client ID not configured")
        return None

    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


# ==============================================================================
# TOOL DEFINITIONS (for LLM)
# ==============================================================================

DB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_play_history",
            "description": "Get recent play history for a user, optionally filtered by mood, artist, or time range. Returns list of recently played songs with metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID to fetch history for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tracks to return (default 20, max 100)",
                        "default": 20
                    },
                    "mood_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific mood UUID"
                    },
                    "artist_name": {
                        "type": "string",
                        "description": "Optional: Filter by artist name (case-insensitive partial match)"
                    },
                    "hours_ago": {
                        "type": "integer",
                        "description": "Optional: Only include plays from last N hours"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_artist_play_count",
            "description": "Count how many times an artist has been played recently. Useful for avoiding repetitive artist selection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "artist_name": {
                        "type": "string",
                        "description": "Artist name to count"
                    },
                    "last_n_tracks": {
                        "type": "integer",
                        "description": "Check within last N tracks (default 10)",
                        "default": 10
                    }
                },
                "required": ["artist_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_songs_in_library",
            "description": "Search for songs in the user's local library by artist, title, genre, or other criteria. Returns available songs that can be played.",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {
                        "type": "string",
                        "description": "Artist name to search for"
                    },
                    "title": {
                        "type": "string",
                        "description": "Song title to search for"
                    },
                    "genre": {
                        "type": "string",
                        "description": "Genre to filter by"
                    },
                    "min_duration": {
                        "type": "integer",
                        "description": "Minimum song duration in seconds"
                    },
                    "max_duration": {
                        "type": "integer",
                        "description": "Maximum song duration in seconds"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_feedback",
            "description": "Get user feedback (likes/dislikes) on songs. Useful for understanding what the user enjoys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "artist_name": {
                        "type": "string",
                        "description": "Optional artist name to filter feedback by"
                    },
                    "feedback_type": {
                        "type": "string",
                        "enum": ["like", "dislike", "all"],
                        "description": "Type of feedback to retrieve (default 'all')",
                        "default": "all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_spotify_context",
            "description": "Get user's Spotify listening data including top artists, genres, and recent tracks. Essential for personalized music selection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_listening_patterns",
            "description": "Analyze user's listening patterns to identify trends, favorite artists, genres, and play times. Returns insights for better song selection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default 30)",
                        "default": 30
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mood_details",
            "description": "Get complete mood information including profile, energy/valence targets, genres, and example artists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood_id": {
                        "type": "string",
                        "description": "Mood UUID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_moods",
            "description": "List all moods for a user with basic information (id, name, is_default, energy_target, valence_target).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Get UserProfile data for personalization including favorite genres/artists/songs, preferences, and demographics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mood_profile",
            "description": "Get MoodProfile for a specific mood including summary_text, weights_json, and version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood_id": {
                        "type": "string",
                        "description": "Mood UUID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_song_details",
            "description": "Get complete song information including metadata, audio features, lyrics analysis, external IDs, and play statistics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_uuid": {
                        "type": "string",
                        "description": "Song UUID"
                    }
                },
                "required": ["song_uuid"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_info",
            "description": "Get session information for context including metadata, current song info, and playback state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional: Specific session UUID"
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "Optional: Only return active sessions (default false)",
                        "default": False
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_track_intents",
            "description": "Get track intents (pending/acquisition tracks) with selection rationale and status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "mood_id": {
                        "type": "string",
                        "description": "Optional: Filter by mood UUID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["PENDING", "ACQUIRED", "FAILED", "CANCELLED"],
                        "description": "Optional: Filter by status"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_feedback_summary",
            "description": "Aggregate feedback statistics for analysis including like/dislike counts, ratios, and recent tracks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID"
                    },
                    "mood_id": {
                        "type": "string",
                        "description": "Optional: Filter by mood UUID"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default 30)",
                        "default": 30
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_spotify_catalog",
            "description": "Search Spotify's music catalog for tracks by artist, genre, or query. Uses the user's Spotify connection when available for personalized results. Returns list of tracks with metadata including title, artist, duration_ms, and genres. Either 'query' or 'artist' must be provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User UUID (optional; used to access Spotify user token when available)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (genre, song title, etc.). Required if 'artist' is not provided."
                    },
                    "artist": {
                        "type": "string",
                        "description": "Search for tracks by specific artist (more reliable than generic search). If provided, returns top tracks by that artist. Required if 'query' is not provided."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 20, max 50)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "market": {
                        "type": "string",
                        "description": "Optional market code (e.g., 'US', 'GB') to localize Spotify results"
                    }
                },
                "required": []  # Neither is strictly required, but at least one must be provided (handled in function)
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_deezer_related_artists",
            "description": "Get related/similar artists from Deezer for music discovery. Returns artists with similar style/genre. Useful for finding alternatives when training moods based on user feedback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist_name": {
                        "type": "string",
                        "description": "Artist name to find similar artists for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of related artists to return (default 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["artist_name"]
            }
        }
    }
]


# ==============================================================================
# TOOL SUBSETS FOR DIFFERENT AGENT TYPES
# ==============================================================================

# Speech writers need: user context, history, feedback, Deezer similarity
SPEECH_TOOLS = [
    tool for tool in DB_TOOLS 
    if tool["function"]["name"] in [
        "get_play_history",
        "get_user_feedback",
        "get_spotify_context",
        "analyze_listening_patterns",
        "get_mood_details",
        "get_deezer_related_artists",  # NEW - for finding similar artists to mention
    ]
]

# Transition planner needs: recent history, patterns, feedback trends
TRANSITION_TOOLS = [
    tool for tool in DB_TOOLS 
    if tool["function"]["name"] in [
        "get_play_history",
        "get_artist_play_count",
        "get_user_feedback",
        "analyze_listening_patterns",
    ]
]


# ==============================================================================
# TOOL IMPLEMENTATIONS
# ==============================================================================

def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse string timestamp to datetime.
    
    Handles ISO format strings like 'YYYY-MM-DDTHH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS.ffffff'.
    """
    if not timestamp_str:
        return None
    
    try:
        # Try ISO format first
        if 'T' in timestamp_str:
            # Remove timezone info if present (Z or +HH:MM)
            clean_str = timestamp_str.split('+')[0].split('Z')[0]
            # Try with microseconds
            try:
                return datetime.fromisoformat(clean_str)
            except ValueError:
                # Try without microseconds
                return datetime.strptime(clean_str, '%Y-%m-%dT%H:%M:%S')
        else:
            # Try simple date format
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return None


async def get_play_history(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
    mood_id: Optional[str] = None,
    artist_name: Optional[str] = None,
    hours_ago: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Get recent play history for a user."""
    try:
        limit = min(limit, 100)  # Cap at 100

        resolved_mood_id = mood_id
        if mood_id:
            try:
                UUID(str(mood_id))
            except (ValueError, TypeError, AttributeError):
                mood_name = str(mood_id).strip()
                if mood_name:
                    mood_result = await db.execute(
                        select(Mood).where(Mood.name.ilike(mood_name))
                    )
                    mood_row = mood_result.scalar_one_or_none()
                    if not mood_row:
                        mood_result = await db.execute(
                            select(Mood).where(Mood.name.ilike(f"%{mood_name}%"))
                        )
                        mood_row = mood_result.scalar_one_or_none()
                    if mood_row:
                        resolved_mood_id = mood_row.id
                    else:
                        logger.warning(
                            f"get_play_history: mood_id '{mood_id}' not found by name; ignoring mood filter"
                        )
                        resolved_mood_id = None
        
        # Join with Song table and load features
        query = (
            select(PlayHistory, Song)
            .join(Song, PlayHistory.song_uuid == Song.uuid, isouter=True)
            .options(selectinload(Song.features))
            .where(PlayHistory.user_id == user_id)
        )
        
        if resolved_mood_id:
            query = query.where(PlayHistory.mood_id == resolved_mood_id)
        
        if artist_name:
            query = query.where(Song.artist.ilike(f"%{artist_name}%"))
        
        # Order by started_at string (lexicographic sort works for ISO format)
        query = query.order_by(desc(PlayHistory.started_at))
        
        # For hours_ago filter, we need to fetch more and filter in Python
        # since started_at is stored as string
        fetch_limit = limit * 10 if hours_ago else limit  # Fetch more if filtering
        query = query.limit(fetch_limit)
        
        result = await db.execute(query)
        all_pairs = result.all()
        
        # Filter by hours_ago if specified
        if hours_ago:
            cutoff = datetime.utcnow() - timedelta(hours=hours_ago)
            filtered_pairs = []
            for play_history, song in all_pairs:
                if play_history.started_at:
                    parsed_time = _parse_timestamp(play_history.started_at)
                    if parsed_time and parsed_time >= cutoff:
                        filtered_pairs.append((play_history, song))
                # Skip entries without timestamp for hours_ago filter
            history_pairs = filtered_pairs[:limit]
        else:
            history_pairs = all_pairs[:limit]
        
        # Helper to parse JSON
        def parse_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        
        return [
            {
                "song_uuid": h.song_uuid,
                "title": song.title if song else None,
                "artist": song.artist if song else None,
                "played_at": h.started_at,  # Return as string (original format)
                "mood_id": h.mood_id,
                "session_id": h.session_id,
                "transition_type": h.transition_type,
                "artwork_url": song.artwork_url if song else None,
                "genres": parse_json(song.genres) if song and song.genres else [],
                "tags": parse_json(song.tags) if song and song.tags else [],
                "external_ids": {
                    "isrc": song.isrc if song else None,
                    "recording_mbid": song.recording_mbid if song else None,
                    "apple_song_id": song.apple_song_id if song else None,
                },
                "features": {
                    "tempo": song.features.tempo if song and song.features else None,
                    "energy": song.features.energy if song and song.features else None,
                    "valence": song.features.valence if song and song.features else None,
                    "danceability": song.features.danceability if song and song.features else None,
                    "acousticness": song.features.acousticness if song and song.features else None,
                } if song and song.features else None,
            }
            for h, song in history_pairs
        ]
    except Exception as e:
        logger.error(f"Error fetching play history: {e}")
        return []


async def get_artist_play_count(
    db: AsyncSession,
    user_id: str,
    artist_name: str,
    last_n_tracks: int = 10,
) -> Dict[str, Any]:
    """Count how many times an artist has been played recently."""
    try:
        # Get last N tracks, joining with Song to get artist
        query = (
            select(PlayHistory, Song)
            .join(Song, PlayHistory.song_uuid == Song.uuid, isouter=True)
            .where(PlayHistory.user_id == user_id)
            .order_by(desc(PlayHistory.started_at))
            .limit(last_n_tracks)
        )
        
        result = await db.execute(query)
        recent_pairs = result.all()
        
        # Count artist occurrences (case-insensitive partial match)
        artist_lower = artist_name.lower().strip()
        count = 0
        for play_history, song in recent_pairs:
            if song and song.artist:
                song_artist_lower = song.artist.lower()
                if (
                    artist_lower in song_artist_lower or
                    song_artist_lower in artist_lower
                ):
                    count += 1
        
        return {
            "artist": artist_name,
            "play_count": count,
            "in_last_n_tracks": last_n_tracks,
            "percentage": (count / last_n_tracks * 100) if last_n_tracks > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error counting artist plays: {e}")
        return {"artist": artist_name, "play_count": 0, "error": str(e)}


async def search_songs_in_library(
    db: AsyncSession,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    genre: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Search for songs in the local library."""
    try:
        # Load SongFeatures and LyricsAnalysis relationships
        query = (
            select(Song)
            .options(selectinload(Song.features), selectinload(Song.lyrics_analysis))
            .where(Song.local_path.isnot(None))
        )
        
        if artist:
            query = query.where(Song.artist.ilike(f"%{artist}%"))
        
        if title:
            query = query.where(Song.title.ilike(f"%{title}%"))
        
        if min_duration:
            query = query.where(Song.duration_sec >= min_duration)
        
        if max_duration:
            query = query.where(Song.duration_sec <= max_duration)
        
        query = query.limit(min(limit, 100))
        
        result = await db.execute(query)
        songs = result.scalars().all()
        
        # Filter by genre in Python (since genres is JSON)
        if genre:
            genre_lower = genre.lower()
            filtered_songs = []
            for song in songs:
                if song.genres:
                    try:
                        genres_list = json.loads(song.genres) if isinstance(song.genres, str) else song.genres
                        if any(genre_lower in g.lower() for g in genres_list):
                            filtered_songs.append(song)
                    except (json.JSONDecodeError, TypeError):
                        # If genres is not valid JSON, check as string
                        if genre_lower in song.genres.lower():
                            filtered_songs.append(song)
                else:
                    # No genres, skip if genre filter specified
                    pass
            songs = filtered_songs[:limit]
        
        # Helper to parse JSON
        def parse_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        
        return [
            {
                "uuid": song.uuid,
                "title": song.title,
                "artist": song.artist,
                "album": None,  # Song model doesn't have album field
                "genre": parse_json(song.genres) if song.genres else [],
                "tags": parse_json(song.tags) if song.tags else [],
                "duration_sec": song.duration_sec,
                "artwork_url": song.artwork_url,
                "bpm": song.features.tempo if song.features else None,
                "energy": song.features.energy if song.features else None,
                "valence": song.features.valence if song.features else None,
                "danceability": song.features.danceability if song.features else None,
                "acousticness": song.features.acousticness if song.features else None,
                "instrumentalness": song.features.instrumentalness if song.features else None,
                "external_ids": {
                    "isrc": song.isrc,
                    "recording_mbid": song.recording_mbid,
                    "apple_song_id": song.apple_song_id,
                },
                "play_statistics": {
                    "play_count": song.play_count,
                    "last_played_at": song.last_played_at,
                },
                "lyrics_analysis": {
                    "themes": parse_json(song.lyrics_analysis.themes) if song.lyrics_analysis else None,
                    "moods": parse_json(song.lyrics_analysis.moods) if song.lyrics_analysis else None,
                    "narrative_style": song.lyrics_analysis.narrative_style if song.lyrics_analysis else None,
                    "emotional_intensity_score": song.lyrics_analysis.emotional_intensity_score if song.lyrics_analysis else None,
                } if song.lyrics_analysis else None,
            }
            for song in songs
        ]
    except Exception as e:
        logger.error(f"Error searching songs: {e}")
        return []


async def get_user_feedback(
    db: AsyncSession,
    user_id: str,
    artist_name: Optional[str] = None,
    feedback_type: str = "all",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Get user feedback on songs."""
    try:
        # Import FeedbackEvent from feedback module
        from backend_v2.models.feedback import FeedbackEvent
        
        query = select(FeedbackEvent).where(FeedbackEvent.user_id == user_id)

        if artist_name:
            query = query.where(FeedbackEvent.track_artist.ilike(f"%{artist_name}%"))
        
        if feedback_type == "like":
            query = query.where(FeedbackEvent.value == "like")
        elif feedback_type == "dislike":
            query = query.where(FeedbackEvent.value == "dislike")
        
        query = query.order_by(desc(FeedbackEvent.created_at)).limit(min(limit, 100))
        
        result = await db.execute(query)
        feedback = result.scalars().all()
        
        return [
            {
                "song_uuid": f.song_uuid,
                "artist": f.track_artist,  # Use track_artist instead of artist
                "title": f.track_title,  # Use track_title instead of title
                "reaction": f.value,  # Use value instead of reaction
                "reason": f.reason_text,  # Include reason_text
                "mood_id": f.mood_id,  # Include mood_id for filtering
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in feedback
        ]
    except Exception as e:
        logger.error(f"Error fetching feedback: {e}")
        return []


async def get_spotify_context(
    db: AsyncSession,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Get user's Spotify listening context."""
    try:
        query = select(SpotifyContext).where(SpotifyContext.user_id == user_id)
        result = await db.execute(query)
        context = result.scalars().first()
        
        if not context:
            return None
        
        # Helper to parse JSON
        def parse_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        
        # Parse top artists JSON
        top_artists_data = parse_json(context.top_artists_json) or {}
        
        # Parse favorite tracks with stats
        favorite_tracks = parse_json(context.favorite_tracks_with_stats_json) or []
        
        # Parse AI-enriched data
        genres_analysis = parse_json(context.genres_analysis_json)
        mood_analysis = parse_json(context.mood_analysis_json)
        listening_habits = parse_json(context.listening_habits_json) or {}
        music_preferences = parse_json(context.music_preferences_json) or {}
        playlists_data = parse_json(context.playlists_json) or {}
        
        return {
            "spotify_id": context.spotify_id,
            "has_spotify": True,
            "top_artists": {
                "short_term": top_artists_data.get("short_term", []),
                "medium_term": top_artists_data.get("medium_term", []),
                "long_term": top_artists_data.get("long_term", []),
            },
            "favorite_tracks_with_stats": favorite_tracks,
            "genres_analysis": genres_analysis,
            "mood_analysis": mood_analysis,
            "listening_habits": listening_habits,
            "music_preferences": music_preferences,
            "playlists": playlists_data,
            "last_updated": context.updated_at.isoformat() if context.updated_at else None,
            "last_synced_at": context.last_synced_at.isoformat() if context.last_synced_at else None,
        }
    except Exception as e:
        logger.error(f"Error fetching Spotify context: {e}")
        return None


async def analyze_listening_patterns(
    db: AsyncSession,
    user_id: str,
    days: int = 30,
) -> Dict[str, Any]:
    """Analyze user's listening patterns."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get all plays, joining with Song and loading features
        # Note: We can't filter by started_at in SQL since it's a string,
        # so we'll fetch more and filter in Python
        query = (
            select(PlayHistory, Song)
            .join(Song, PlayHistory.song_uuid == Song.uuid, isouter=True)
            .options(selectinload(Song.features))
            .where(PlayHistory.user_id == user_id)
            .order_by(desc(PlayHistory.started_at))
            .limit(10000)  # Fetch a large batch for analysis
        )
        
        result = await db.execute(query)
        all_pairs = result.all()
        
        # Filter by date range in Python (parse started_at strings)
        plays = []
        for play_history, song in all_pairs:
            if play_history.started_at:
                parsed_time = _parse_timestamp(play_history.started_at)
                if parsed_time and parsed_time >= cutoff:
                    plays.append((play_history, song))
        
        if not plays:
            return {"error": "No play history in specified time range"}
        
        # Analyze patterns
        artist_counts = {}
        hour_distribution = [0] * 24
        mood_counts = {}
        genre_counts = {}
        energy_values = []
        valence_values = []
        
        # Helper to parse JSON
        def parse_json(val: Optional[str]) -> List[str]:
            if not val:
                return []
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        
        for play_history, song in plays:
            # Count artists (from Song table)
            if song and song.artist:
                artist_counts[song.artist] = artist_counts.get(song.artist, 0) + 1
            
            # Count moods
            if play_history.mood_id:
                mood_counts[play_history.mood_id] = mood_counts.get(play_history.mood_id, 0) + 1
            
            # Count genres (from Song.genres JSON)
            if song and song.genres:
                genres = parse_json(song.genres)
                for genre in genres:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
            
            # Collect energy/valence values for trends
            if song and song.features:
                if song.features.energy is not None:
                    energy_values.append(song.features.energy)
                if song.features.valence is not None:
                    valence_values.append(song.features.valence)
            
            # Track hourly distribution (parse started_at)
            if play_history.started_at:
                parsed_time = _parse_timestamp(play_history.started_at)
                if parsed_time:
                    hour = parsed_time.hour
                    hour_distribution[hour] += 1
        
        # Top artists
        top_artists = sorted(
            artist_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Top moods (need to fetch mood names)
        top_mood_ids = sorted(
            mood_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # Get mood names for top moods
        mood_names = {}
        if top_mood_ids:
            mood_ids_list = [mood_id for mood_id, _ in top_mood_ids]
            mood_query = select(Mood).where(Mood.id.in_(mood_ids_list))
            mood_result = await db.execute(mood_query)
            moods = mood_result.scalars().all()
            mood_names = {mood.id: mood.name for mood in moods}
        
        top_moods = [
            {"mood_id": mood_id, "mood_name": mood_names.get(mood_id, "Unknown"), "play_count": count}
            for mood_id, count in top_mood_ids
        ]
        
        # Top genres
        top_genres = sorted(
            genre_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Find peak listening hours
        if max(hour_distribution) > 0:
            peak_hour = hour_distribution.index(max(hour_distribution))
        else:
            peak_hour = None
        
        # Calculate energy/valence averages
        avg_energy = sum(energy_values) / len(energy_values) if energy_values else None
        avg_valence = sum(valence_values) / len(valence_values) if valence_values else None
        
        return {
            "total_plays": len(plays),
            "unique_artists": len(artist_counts),
            "top_artists": [
                {"artist": artist, "play_count": count}
                for artist, count in top_artists
            ],
            "peak_listening_hour": peak_hour,
            "hourly_distribution": hour_distribution,
            "days_analyzed": days,
            "mood_analysis": {
                "unique_moods": len(mood_counts),
                "top_moods": top_moods,
            },
            "genre_distribution": [
                {"genre": genre, "play_count": count}
                for genre, count in top_genres
            ],
            "energy_trends": {
                "average_energy": round(avg_energy, 3) if avg_energy is not None else None,
                "samples_count": len(energy_values),
            },
            "valence_trends": {
                "average_valence": round(avg_valence, 3) if avg_valence is not None else None,
                "samples_count": len(valence_values),
            },
        }
    except Exception as e:
        logger.error(f"Error analyzing listening patterns: {e}")
        return {"error": str(e)}


# ==============================================================================
# NEW TOOL IMPLEMENTATIONS
# ==============================================================================

async def get_mood_details(
    db: AsyncSession,
    mood_id: str,
) -> Optional[Dict[str, Any]]:
    """Get complete mood information including profile."""
    try:
        query = (
            select(Mood)
            .options(selectinload(Mood.profile))
            .where(Mood.id == mood_id)
        )
        result = await db.execute(query)
        mood = result.scalar_one_or_none()
        
        if not mood:
            return None
        
        # Parse JSON fields
        def parse_json_list(val: Optional[str]) -> List[str]:
            if not val:
                return []
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        
        genres = parse_json_list(mood.genres_json)
        genre_seeds = parse_json_list(mood.genre_seeds_json)
        vibe_keywords = parse_json_list(mood.vibe_keywords_json)
        avoid_genres = parse_json_list(mood.avoid_genres_json)
        example_artists = parse_json_list(mood.example_artists_json)
        
        # Parse MoodProfile weights_json
        weights = None
        if mood.profile and mood.profile.weights_json:
            try:
                weights = json.loads(mood.profile.weights_json)
            except json.JSONDecodeError:
                weights = None
        
        return {
            "mood_id": mood.id,
            "name": mood.name,
            "color": mood.color,
            "energy_target": mood.energy_target,
            "valence_target": mood.valence_target,
            "danceability_target": mood.danceability_target,
            "tempo_min": mood.tempo_min,
            "tempo_max": mood.tempo_max,
            "genres": genres,
            "genre_seeds": genre_seeds,
            "vibe_keywords": vibe_keywords,
            "avoid_genres": avoid_genres,
            "example_artists": example_artists,
            "intro_personality": mood.intro_personality,
            "era_hint": mood.era_hint,
            "dj_personality": mood.dj_personality,
            "is_default": mood.is_default,
            "profile": {
                "summary_text": mood.profile.summary_text if mood.profile else None,
                "weights_json": weights,
                "version": mood.profile.version if mood.profile else 1,
                "updated_at": mood.profile.updated_at.isoformat() if mood.profile and mood.profile.updated_at else None,
            } if mood.profile else None,
        }
    except Exception as e:
        logger.error(f"Error fetching mood details: {e}")
        return None


async def get_user_moods(
    db: AsyncSession,
    user_id: str,
) -> List[Dict[str, Any]]:
    """List all moods for a user."""
    try:
        query = select(Mood).where(Mood.user_id == user_id).order_by(Mood.is_default.desc(), Mood.created_at.desc())
        result = await db.execute(query)
        moods = result.scalars().all()
        
        return [
            {
                "mood_id": mood.id,
                "name": mood.name,
                "is_default": mood.is_default,
                "energy_target": mood.energy_target,
                "valence_target": mood.valence_target,
                "dj_personality": mood.dj_personality,
                "color": mood.color,
            }
            for mood in moods
        ]
    except Exception as e:
        logger.error(f"Error fetching user moods: {e}")
        return []


async def get_user_profile(
    db: AsyncSession,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Get UserProfile data for personalization."""
    try:
        query = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            return None
        
        # Parse JSON arrays
        def parse_json_list(val: Optional[str]) -> List[str]:
            if not val:
                return []
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        
        return {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "age_range": profile.age_range,
            "location": profile.location,
            "occupation": profile.occupation,
            "favorite_genres": parse_json_list(profile.favorite_genres),
            "favorite_artists": parse_json_list(profile.favorite_artists),
            "favorite_songs": parse_json_list(profile.favorite_songs),
            "no_go": parse_json_list(profile.no_go),
            "explicit_lyrics": profile.explicit_lyrics or "ok",
            "dj_personality": profile.dj_personality or "casual_funny",
            "raw_context": profile.raw_context,
            "energy_preference": profile.energy_preference,
            "tempo_preference": profile.tempo_preference,
            "listening_contexts": parse_json_list(profile.listening_contexts),
            "era_preference": profile.era_preference or "mixed",
        }
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return None


async def get_mood_profile(
    db: AsyncSession,
    mood_id: str,
) -> Optional[Dict[str, Any]]:
    """Get MoodProfile for a specific mood."""
    try:
        query = select(MoodProfile).where(MoodProfile.mood_id == mood_id)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            return None
        
        # Parse weights_json
        weights = None
        if profile.weights_json:
            try:
                weights = json.loads(profile.weights_json)
            except json.JSONDecodeError:
                weights = None
        
        return {
            "mood_id": profile.mood_id,
            "summary_text": profile.summary_text,
            "weights_json": weights,
            "version": profile.version,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
    except Exception as e:
        logger.error(f"Error fetching mood profile: {e}")
        return None


async def get_song_details(
    db: AsyncSession,
    song_uuid: str,
) -> Optional[Dict[str, Any]]:
    """Get complete song information including features and lyrics analysis."""
    try:
        query = (
            select(Song)
            .options(selectinload(Song.features), selectinload(Song.lyrics_analysis))
            .where(Song.uuid == song_uuid)
        )
        result = await db.execute(query)
        song = result.scalar_one_or_none()
        
        if not song:
            return None
        
        # Parse JSON fields
        def parse_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        
        genres = parse_json(song.genres) if song.genres else []
        tags = parse_json(song.tags) if song.tags else []
        
        # Parse LyricsAnalysis JSON fields
        lyrics_data = None
        if song.lyrics_analysis:
            lyrics_data = {
                "themes": parse_json(song.lyrics_analysis.themes),
                "moods": parse_json(song.lyrics_analysis.moods),
                "brands": parse_json(song.lyrics_analysis.brands),
                "locations": parse_json(song.lyrics_analysis.locations),
                "cultural_ref_people": parse_json(song.lyrics_analysis.cultural_ref_people),
                "cultural_ref_non_people": parse_json(song.lyrics_analysis.cultural_ref_non_people),
                "narrative_style": song.lyrics_analysis.narrative_style,
                "emotional_intensity_score": song.lyrics_analysis.emotional_intensity_score,
                "imagery_score": song.lyrics_analysis.imagery_score,
                "complexity_score": song.lyrics_analysis.complexity_score,
                "rhyme_scheme_score": song.lyrics_analysis.rhyme_scheme_score,
                "repetitiveness_score": song.lyrics_analysis.repetitiveness_score,
            }
        
        # SongFeatures data
        features = None
        if song.features:
            features = {
                "tempo": song.features.tempo,
                "energy": song.features.energy,
                "valence": song.features.valence,
                "danceability": song.features.danceability,
                "acousticness": song.features.acousticness,
                "instrumentalness": song.features.instrumentalness,
                "key": song.features.key,
                "mode": song.features.mode,
                "liveness": song.features.liveness,
                "loudness": song.features.loudness,
                "speechiness": song.features.speechiness,
                "time_signature": song.features.time_signature,
            }
        
        return {
            "uuid": song.uuid,
            "title": song.title,
            "artist": song.artist,
            "release_date": song.release_date,
            "language_code": song.language_code,
            "explicit": bool(song.explicit) if song.explicit else False,
            "duration_sec": song.duration_sec,
            "filesize_bytes": song.filesize_bytes,
            "play_count": song.play_count,
            "last_played_at": song.last_played_at,
            "genres": genres,
            "tags": tags,
            "artwork_url": song.artwork_url,
            "external_ids": {
                "isrc": song.isrc,
                "recording_mbid": song.recording_mbid,
                "release_mbid": song.release_mbid,
                "artist_mbid": song.artist_mbid,
                "apple_song_id": song.apple_song_id,
            },
            "features": features,
            "lyrics_analysis": lyrics_data,
        }
    except Exception as e:
        logger.error(f"Error fetching song details: {e}")
        return None


async def get_session_info(
    db: AsyncSession,
    user_id: str,
    session_id: Optional[str] = None,
    active_only: bool = False,
) -> List[Dict[str, Any]]:
    """Get session information for context."""
    try:
        query = select(Session).where(Session.user_id == user_id)
        
        if session_id:
            query = query.where(Session.session_id == session_id)
        
        if active_only:
            query = query.where(Session.is_active == 1)
        
        query = query.order_by(desc(Session.started_at))
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        return [
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "mood_id": session.mood_id,
                "context_id": session.context_id,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "mode": session.mode,
                "session_summary": session.session_summary,
                "current_song_uuid": session.current_song_uuid,
                "current_song_title": session.current_song_title,
                "current_song_artist": session.current_song_artist,
                "current_song_artwork": session.current_song_artwork,
                "playback_position_sec": session.playback_position_sec,
                "is_active": bool(session.is_active),
                "last_heartbeat_at": session.last_heartbeat_at,
            }
            for session in sessions
        ]
    except Exception as e:
        logger.error(f"Error fetching session info: {e}")
        return []


async def get_track_intents(
    db: AsyncSession,
    user_id: str,
    mood_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get track intents (pending/acquisition tracks)."""
    try:
        query = select(TrackIntent).where(TrackIntent.user_id == user_id)
        
        if mood_id:
            query = query.where(TrackIntent.mood_id == mood_id)
        
        if status:
            query = query.where(TrackIntent.status == status)
        
        query = query.order_by(desc(TrackIntent.created_at)).limit(min(limit, 100))
        
        result = await db.execute(query)
        intents = result.scalars().all()
        
        return [
            {
                "intent_id": intent.id,
                "user_id": intent.user_id,
                "mood_id": intent.mood_id,
                "session_id": intent.session_id,
                "title": intent.title,
                "artist": intent.artist,
                "album": intent.album,
                "spotify_id": intent.spotify_id,
                "apple_music_id": intent.apple_music_id,
                "isrc": intent.isrc,
                "target_energy": intent.target_energy,
                "target_valence": intent.target_valence,
                "target_tempo": intent.target_tempo,
                "target_danceability": intent.target_danceability,
                "status": intent.status,
                "acquired_song_uuid": intent.acquired_song_uuid,
                "selection_rationale": intent.selection_rationale,
                "selection_method": intent.selection_method,
                "failure_reason": intent.failure_reason,
                "created_at": intent.created_at.isoformat() if intent.created_at else None,
                "resolved_at": intent.resolved_at.isoformat() if intent.resolved_at else None,
            }
            for intent in intents
        ]
    except Exception as e:
        logger.error(f"Error fetching track intents: {e}")
        return []


async def get_feedback_summary(
    db: AsyncSession,
    user_id: str,
    mood_id: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """Aggregate feedback statistics for analysis."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = select(FeedbackEvent).where(FeedbackEvent.user_id == user_id)
        
        if mood_id:
            query = query.where(FeedbackEvent.mood_id == mood_id)
        
        query = query.order_by(desc(FeedbackEvent.created_at)).limit(1000)
        
        result = await db.execute(query)
        all_feedback = result.scalars().all()
        
        # Filter by date range
        feedback = []
        for f in all_feedback:
            if f.created_at and f.created_at >= cutoff:
                feedback.append(f)
        
        if not feedback:
            return {
                "total_feedback": 0,
                "likes": 0,
                "dislikes": 0,
                "like_ratio": 0.0,
                "recent_liked_tracks": [],
                "recent_disliked_tracks": [],
                "days_analyzed": days,
            }
        
        # Count likes and dislikes
        likes = [f for f in feedback if f.value == "like"]
        dislikes = [f for f in feedback if f.value == "dislike"]
        
        # Get recent liked/disliked tracks
        recent_liked = [
            {
                "artist": f.track_artist,
                "title": f.track_title,
                "song_uuid": f.song_uuid,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in likes[:5]
            if f.track_artist and f.track_title
        ]
        
        recent_disliked = [
            {
                "artist": f.track_artist,
                "title": f.track_title,
                "song_uuid": f.song_uuid,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in dislikes[:5]
            if f.track_artist and f.track_title
        ]
        
        total = len(feedback)
        like_ratio = (len(likes) / total * 100) if total > 0 else 0.0
        
        return {
            "total_feedback": total,
            "likes": len(likes),
            "dislikes": len(dislikes),
            "like_ratio": round(like_ratio, 2),
            "recent_liked_tracks": recent_liked,
            "recent_disliked_tracks": recent_disliked,
            "days_analyzed": days,
        }
    except Exception as e:
        logger.error(f"Error fetching feedback summary: {e}")
        return {"error": str(e)}


async def search_spotify_catalog(
    db: AsyncSession,
    user_id: Optional[str] = None,
    query: Optional[str] = None,
    artist: Optional[str] = None,
    limit: int = 20,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search Spotify catalog for tracks.

    Args:
        db: Database session
        user_id: Optional user UUID (used to access Spotify user token)
        query: Optional search query (genre, artist name, song title, etc.). Required if artist is not provided.
        artist: Optional artist name for artist-specific search. Required if query is not provided.
        limit: Maximum results to return (default 20, max 50)
        market: Optional market code for localized results (e.g., "US", "GB")

    Returns:
        List of track dictionaries with metadata
    """
    try:
        import httpx
        from backend_v2.utils.time import ensure_utc, utc_now
        from backend_v2.integrations.metadata.spotify_metadata import get_spotify_metadata_client

        # Validate that at least one search parameter is provided
        if not query and not artist:
            logger.warning("search_spotify_catalog: Either 'query' or 'artist' must be provided")
            return []

        # Limit to max 50 (Spotify limit)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 50))

        access_token = None
        spotify_context = None

        # Prefer user-specific Spotify token if available
        if user_id:
            result = await db.execute(
                select(SpotifyContext).where(SpotifyContext.user_id == user_id)
            )
            spotify_context = result.scalars().first()
            if spotify_context and spotify_context.access_token:
                access_token = spotify_context.access_token

                token_expires_at = ensure_utc(spotify_context.token_expires_at)
                if token_expires_at and utc_now() >= token_expires_at:
                    spotify_client = _get_spotify_oauth_client()
                    if spotify_client:
                        try:
                            token_data = await spotify_client.refresh_access_token(
                                spotify_context.refresh_token
                            )
                            access_token = token_data.get("access_token") or access_token
                        except Exception as refresh_error:
                            logger.warning(f"Spotify token refresh failed: {refresh_error}")

        # Fallback to app-level token if user token is unavailable
        if not access_token:
            metadata_client = get_spotify_metadata_client()
            if metadata_client and metadata_client.enabled:
                access_token = await metadata_client._get_access_token()

        if not access_token:
            logger.warning("Spotify access token unavailable for search_spotify_catalog")
            return []

        # Build search query
        if artist and query:
            search_query = f'{query} artist:"{artist}"'
        elif artist:
            search_query = f'artist:"{artist}"'
        else:
            search_query = query

        if not search_query:
            logger.warning("search_spotify_catalog: Empty search query after normalization")
            return []

        async with httpx.AsyncClient() as client:
            params = {
                "q": search_query,
                "type": "track",
                "limit": limit,
            }
            if market:
                params["market"] = market

            response = await client.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=30.0,
            )

            if response.status_code == 401 and spotify_context:
                spotify_client = _get_spotify_oauth_client()
                if spotify_client:
                    try:
                        token_data = await spotify_client.refresh_access_token(
                            spotify_context.refresh_token
                        )
                        refreshed_token = token_data.get("access_token")
                        if refreshed_token:
                            access_token = refreshed_token
                            response = await client.get(
                                "https://api.spotify.com/v1/search",
                                headers={"Authorization": f"Bearer {access_token}"},
                                params=params,
                                timeout=30.0,
                            )
                    except Exception as refresh_error:
                        logger.warning(f"Spotify token refresh failed: {refresh_error}")

            response.raise_for_status()
            data = response.json()
            items = data.get("tracks", {}).get("items", [])

            if not items:
                return []

            track_ids = [item.get("id") for item in items if item.get("id")]
            features_by_id: Dict[str, Dict[str, Any]] = {}

            if track_ids:
                try:
                    features_response = await client.get(
                        "https://api.spotify.com/v1/audio-features",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"ids": ",".join(track_ids[:100])},
                        timeout=30.0,
                    )
                    if features_response.status_code == 200:
                        features_payload = features_response.json()
                        for feat in features_payload.get("audio_features", []) or []:
                            if feat and feat.get("id"):
                                features_by_id[feat["id"]] = feat
                except Exception as features_error:
                    logger.warning(f"Spotify audio features lookup failed: {features_error}")

            results = []
            for item in items:
                if not item:
                    continue

                artists = [
                    artist_obj.get("name")
                    for artist_obj in item.get("artists", [])
                    if artist_obj.get("name")
                ]
                artist_name = ", ".join(artists) if artists else None
                album = item.get("album") or {}
                images = album.get("images") or []
                artwork_url = images[0].get("url") if images else None
                track_id = item.get("id")

                track_dict = {
                    "title": item.get("name"),
                    "artist": artist_name,
                    "provider_id": track_id,
                    "duration_ms": item.get("duration_ms"),
                    "genres": [],
                }

                album_name = album.get("name")
                if album_name:
                    track_dict["album"] = album_name

                if artwork_url:
                    track_dict["artwork_url"] = artwork_url

                preview_url = item.get("preview_url")
                if preview_url:
                    track_dict["preview_url"] = preview_url

                if track_id and track_id in features_by_id:
                    feat = features_by_id[track_id]
                    track_dict["features"] = {
                        "energy": feat.get("energy"),
                        "valence": feat.get("valence"),
                        "tempo": feat.get("tempo"),
                        "danceability": feat.get("danceability"),
                    }

                results.append(track_dict)

            search_desc = f"'{query}'" if query else ""
            artist_desc = f" (artist: '{artist}')" if artist else ""
            logger.info(f"Spotify search {search_desc}{artist_desc}: found {len(results)} tracks")
            return results

    except Exception as e:
        logger.error(f"Error searching Spotify catalog: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def search_deezer_catalog(
    db: AsyncSession,
    query: Optional[str] = None,
    artist: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Search Deezer catalog for tracks.
    
    Args:
        db: Database session (not used but required for tool signature)
        query: Optional search query (artist name, genre, song title, etc.). Required if artist is not provided.
        artist: Optional artist name for artist-specific search. If provided, returns top tracks by that artist.
        limit: Maximum results to return (default 20, max 100)
        
    Returns:
        List of track dictionaries with metadata
    """
    try:
        from backend_v2.catalog.providers import get_deezer_provider
        
        provider = get_deezer_provider()
        if not provider.enabled:
            logger.warning("Deezer provider not enabled")
            return []
        
        # Validate that at least one search parameter is provided
        if not query and not artist:
            logger.warning("search_deezer_catalog: Either 'query' or 'artist' must be provided")
            return []
        
        # Limit to max 100
        limit = min(limit, 100)
        
        # If artist is provided, use artist-specific search (more reliable)
        if artist:
            tracks = await provider.get_artist_tracks(artist, limit=limit)
        else:
            # Generic search (query is guaranteed to be set here)
            tracks = await provider.search_tracks(query, limit=limit)
        
        if not tracks:
            return []
        
        # Convert CatalogTrack objects to dict format for LLM
        results = []
        for track in tracks:
            track_dict = {
                "title": track.title,
                "artist": track.artist,
                "provider_id": track.provider_id,
                "duration_ms": track.duration_ms,  # Fixed: CatalogTrack has duration_ms, not duration
                "genres": track.genres or [],
            }
            
            # Add album if available
            if track.album:
                track_dict["album"] = track.album
            
            # Add artwork URL if available
            if track.artwork_url:
                track_dict["artwork_url"] = track.artwork_url
            
            # Add features if available
            if track.features:
                track_dict["features"] = {
                    "energy": track.features.energy,
                    "valence": track.features.valence,
                    "tempo": track.features.tempo,
                    "danceability": track.features.danceability,
                }
            
            results.append(track_dict)
        
        search_desc = f"'{query}'" if query else ""
        artist_desc = f" (artist: '{artist}')" if artist else ""
        logger.info(f"🔍 Deezer search {search_desc}{artist_desc}: found {len(results)} tracks")
        return results
        
    except Exception as e:
        logger.error(f"Error searching Deezer catalog: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def get_deezer_related_artists(
    db: AsyncSession,
    artist_name: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Get related/similar artists from Deezer.
    
    Args:
        db: Database session (not used, but required for tool interface)
        artist_name: Artist name to find similar artists for
        limit: Maximum number of related artists to return (default 10)
        
    Returns:
        List of related artist objects with id, name, picture, nb_fan
    """
    try:
        from backend_v2.integrations.deezer import get_deezer_client
        deezer = get_deezer_client()
        
        # First, search for the artist to get their ID
        artist = await deezer.search_artist(artist_name)
        if not artist:
            logger.warning(f"Artist not found on Deezer: {artist_name}")
            return []
        
        artist_id = artist["id"]
        logger.info(f"Found artist {artist_name} (id={artist_id}) on Deezer")
        
        # Get related artists
        related_artists = await deezer.get_related_artists(artist_id, limit=limit)
        
        if not related_artists:
            logger.info(f"No related artists found for {artist_name}")
            return []
        
        logger.info(f"Found {len(related_artists)} related artists for {artist_name}")
        return related_artists
        
    except Exception as e:
        logger.error(f"Error getting Deezer related artists: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


# ==============================================================================
# TOOL EXECUTOR
# ==============================================================================

TOOL_MAPPING = {
    "get_play_history": get_play_history,
    "get_artist_play_count": get_artist_play_count,
    "search_songs_in_library": search_songs_in_library,
    "get_user_feedback": get_user_feedback,
    "get_spotify_context": get_spotify_context,
    "analyze_listening_patterns": analyze_listening_patterns,
    "get_mood_details": get_mood_details,
    "get_user_moods": get_user_moods,
    "get_user_profile": get_user_profile,
    "get_mood_profile": get_mood_profile,
    "get_song_details": get_song_details,
    "get_session_info": get_session_info,
    "get_track_intents": get_track_intents,
    "get_feedback_summary": get_feedback_summary,
    "search_spotify_catalog": search_spotify_catalog,
    "get_deezer_related_artists": get_deezer_related_artists,
}


async def execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    db: AsyncSession,
    # Logging parameters
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mood_id: Optional[str] = None,
    llm_trace_id: Optional[int] = None,
    agent_name: Optional[str] = None,
    auto_log: bool = True,
) -> Any:
    """Execute a tool by name with provided arguments.
    
    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool
        db: Database session
        session_id: Optional session ID for logging
        user_id: Optional user ID for logging
        mood_id: Optional mood ID for logging
        llm_trace_id: Optional LLM trace ID this tool call is associated with
        agent_name: Optional agent name for logging
        auto_log: Whether to automatically log this tool execution
        
    Returns:
        Tool execution result
    """
    if tool_name not in TOOL_MAPPING:
        raise ValueError(f"Unknown tool: {tool_name}")
    
    tool_func = TOOL_MAPPING[tool_name]

    if user_id:
        params = inspect.signature(tool_func).parameters
        if "user_id" in params:
            arg_user_id = tool_args.get("user_id")
            placeholder_ids = {"user_id", "userid", "unknown", "none", "null", ""}
            if (
                arg_user_id is None
                or str(arg_user_id).strip().lower() in placeholder_ids
                or not _is_uuid(arg_user_id)
            ):
                tool_args["user_id"] = user_id

    if mood_id:
        params = inspect.signature(tool_func).parameters
        if "mood_id" in params:
            arg_mood_id = tool_args.get("mood_id")
            placeholder_moods = {"mood_id", "moodid", "unknown", "none", "null", ""}
            if (
                arg_mood_id is None
                or str(arg_mood_id).strip().lower() in placeholder_moods
                or not _is_uuid(arg_mood_id)
            ):
                tool_args["mood_id"] = mood_id
    
    import time
    start_time = time.time()
    success = True
    error_message = None
    result = None
    
    try:
        result = await tool_func(db=db, **tool_args)
        execution_time_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ Executed tool: {tool_name} ({execution_time_ms:.1f}ms)")
        
        # Auto-log tool execution
        if auto_log:
            try:
                from backend_v2.integrations.openrouter import store_tool_usage_log
                await store_tool_usage_log(
                    db=db,
                    tool_name=tool_name,
                    tool_arguments=tool_args,
                    tool_result=result,
                    session_id=session_id,
                    user_id=user_id,
                    mood_id=mood_id,
                    llm_trace_id=llm_trace_id,
                    agent_name=agent_name,
                    execution_time_ms=execution_time_ms,
                    success=True,
                )
            except Exception as e:
                logger.warning(f"Failed to log tool execution: {e}")
        
        return result
    except Exception as e:
        success = False
        error_message = str(e)
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ Tool execution failed: {tool_name} - {e} ({execution_time_ms:.1f}ms)")
        
        # Log failed tool execution
        if auto_log:
            try:
                from backend_v2.integrations.openrouter import store_tool_usage_log
                await store_tool_usage_log(
                    db=db,
                    tool_name=tool_name,
                    tool_arguments=tool_args,
                    tool_result=None,
                    session_id=session_id,
                    user_id=user_id,
                    mood_id=mood_id,
                    llm_trace_id=llm_trace_id,
                    agent_name=agent_name,
                    execution_time_ms=execution_time_ms,
                    success=False,
                    error_message=error_message,
                )
            except Exception as log_error:
                logger.warning(f"Failed to log failed tool execution: {log_error}")
        
        raise
