"""Simplified JSON Schema for Spotify enrichment - OpenRouter structured outputs compatible.

Follows OpenRouter/OpenAI strict JSON schema requirements:
- additionalProperties: false on all objects
- All properties listed in 'required'
"""
from typing import Dict, Any


def get_enrichment_schema() -> Dict[str, Any]:
    """Get simplified JSON Schema for Spotify data enrichment output.
    
    Returns:
        JSON Schema dict compatible with OpenRouter's strict json_schema format
    """
    return {
        "type": "object",
        "properties": {
            "favorite_artists": {
                "type": "array",
                "description": "Top 5 favorite artists",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Artist name"},
                        "genres": {"type": "string", "description": "Main genres"},
                        "why_favorite": {"type": "string", "description": "Why they're a favorite"}
                    },
                    "required": ["name", "genres", "why_favorite"],
                    "additionalProperties": False
                }
            },
            "favorite_songs": {
                "type": "array",
                "description": "Top 5 favorite songs",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Song title"},
                        "artist": {"type": "string", "description": "Artist name"},
                        "why_favorite": {"type": "string", "description": "Why it's a favorite"}
                    },
                    "required": ["title", "artist", "why_favorite"],
                    "additionalProperties": False
                }
            },
            "music_preferences": {
                "type": "object",
                "description": "Overall music preferences",
                "properties": {
                    "genres": {"type": "string", "description": "Comma-separated list of preferred genres"},
                    "energy_levels": {"type": "string", "description": "Preferred energy levels (high/medium/low)"},
                    "mood_preferences": {"type": "string", "description": "Preferred moods"}
                },
                "required": ["genres", "energy_levels", "mood_preferences"],
                "additionalProperties": False
            },
            "listening_habits": {
                "type": "object",
                "description": "Listening behavior patterns",
                "properties": {
                    "listening_frequency": {"type": "string", "description": "How often they listen"},
                    "discovery_methods": {"type": "string", "description": "How they find new music"},
                    "playlist_vs_album": {"type": "string", "description": "Preference for playlists vs albums"}
                },
                "required": ["listening_frequency", "discovery_methods", "playlist_vs_album"],
                "additionalProperties": False
            },
            "genres_analysis": {
                "type": "object",
                "description": "Genre breakdown",
                "properties": {
                    "primary_genres": {"type": "string", "description": "Top 3 genres"},
                    "genre_diversity": {"type": "string", "description": "focused/diverse/eclectic"}
                },
                "required": ["primary_genres", "genre_diversity"],
                "additionalProperties": False
            },
            "mood_analysis": {
                "type": "object",
                "description": "Mood patterns",
                "properties": {
                    "dominant_moods": {"type": "string", "description": "Primary moods in listening"},
                    "mood_patterns": {"type": "string", "description": "When and how mood affects listening"}
                },
                "required": ["dominant_moods", "mood_patterns"],
                "additionalProperties": False
            },
            "user_profile_summary": {
                "type": "object",
                "description": "Summary of the listener",
                "properties": {
                    "listener_type": {"type": "string", "description": "casual/enthusiast/power user"},
                    "music_taste_summary": {"type": "string", "description": "One paragraph summary of their taste"}
                },
                "required": ["listener_type", "music_taste_summary"],
                "additionalProperties": False
            }
        },
        "required": [
            "favorite_artists",
            "favorite_songs", 
            "music_preferences",
            "listening_habits",
            "genres_analysis",
            "mood_analysis",
            "user_profile_summary"
        ],
        "additionalProperties": False
    }
