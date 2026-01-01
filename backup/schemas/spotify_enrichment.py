"""JSON Schema definitions for structured output from OpenRouter AI for Spotify enrichment.

Defines comprehensive schema for music preferences, profile summary, and detailed analysis.
"""
from typing import Dict, Any


def get_enrichment_schema() -> Dict[str, Any]:
    """Get expanded JSON Schema for Spotify data enrichment output.
    
    Returns:
        JSON Schema dict compatible with OpenRouter's response_format
    """
    return {
        "type": "object",
        "properties": {
            "favorite_artists": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "spotify_id": {"type": "string"},
                        "genres": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "popularity": {"type": "number"},
                        "followers": {"type": "number"},
                        "why_favorite": {"type": "string", "description": "Why this artist is a favorite"}
                    },
                    "required": ["name"]
                },
                "description": "List of favorite artists with detailed information"
            },
            "favorite_songs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "artist": {"type": "string"},
                        "spotify_id": {"type": "string"},
                        "album": {"type": "string"},
                        "genres": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "popularity": {"type": "number"},
                        "why_favorite": {"type": "string", "description": "Why this song is a favorite"}
                    },
                    "required": ["name", "artist"]
                },
                "description": "List of favorite songs with detailed information"
            },
            "last_listened_to": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "track_name": {"type": "string"},
                        "artist": {"type": "string"},
                        "played_at": {"type": "string"},
                        "context": {"type": "string", "description": "Where it was played (playlist, album, etc.)"}
                    },
                    "required": ["track_name", "artist"]
                },
                "description": "Recently played tracks with context"
            },
            "top_played": {
                "type": "object",
                "properties": {
                    "short_term": {
                        "type": "object",
                        "properties": {
                            "top_tracks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "artist": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            },
                            "top_artists": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "medium_term": {
                        "type": "object",
                        "properties": {
                            "top_tracks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "artist": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            },
                            "top_artists": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "long_term": {
                        "type": "object",
                        "properties": {
                            "top_tracks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "artist": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            },
                            "top_artists": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "rank": {"type": "number"}
                                    }
                                }
                            }
                        }
                    }
                },
                "description": "Top played tracks and artists across different time ranges"
            },
            "favorite_tracks_stats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "artist": {"type": "string"},
                        "rank": {"type": "number"},
                        "time_range": {"type": "string", "enum": ["short_term", "medium_term", "long_term"]},
                        "isrc": {"type": "string"}
                    },
                    "required": ["title", "artist", "rank", "time_range"]
                },
                "description": "Favorite tracks with play statistics for DJ speech hooks"
            },
            "user_profile_summary": {
                "type": "object",
                "properties": {
                    "display_name": {"type": "string"},
                    "country": {"type": "string"},
                    "product": {"type": "string", "description": "Spotify subscription type"},
                    "listener_type": {"type": "string", "description": "e.g., 'casual', 'enthusiast', 'power user'"},
                    "music_discovery_style": {"type": "string", "description": "How they discover music"},
                    "listening_patterns": {"type": "string", "description": "When and how they listen"}
                },
                "required": ["display_name"]
            },
            "playlist_analysis": {
                "type": "object",
                "properties": {
                    "total_playlists": {"type": "number"},
                    "playlist_themes": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "favorite_playlists": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "track_count": {"type": "number"}
                            }
                        }
                    },
                    "playlist_creation_style": {"type": "string", "description": "How they organize playlists"}
                }
            },
            "music_preferences": {
                "type": "object",
                "properties": {
                    "genres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of preferred music genres"
                    },
                    "energy_levels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Preferred energy levels (e.g., 'high', 'medium', 'low')"
                    },
                    "mood_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Preferred moods (e.g., 'upbeat', 'chill', 'energetic')"
                    },
                    "tempo_range": {
                        "type": "object",
                        "properties": {
                            "min_bpm": {"type": "number", "description": "Minimum BPM preference"},
                            "max_bpm": {"type": "number", "description": "Maximum BPM preference"}
                        },
                        "description": "Preferred tempo range in BPM"
                    },
                    "decade_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Preferred music decades (e.g., '80s', '90s', '2000s')"
                    }
                },
                "required": ["genres", "energy_levels", "mood_preferences"]
            },
            "listening_habits": {
                "type": "object",
                "properties": {
                    "primary_listening_time": {"type": "string", "description": "When they listen most"},
                    "listening_frequency": {"type": "string", "description": "How often they listen"},
                    "playlist_vs_album": {"type": "string", "description": "Preference for playlists vs albums"},
                    "discovery_methods": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "How they discover new music"
                    },
                    "repeat_behavior": {"type": "string", "description": "How often they replay songs"}
                }
            },
            "genres_analysis": {
                "type": "object",
                "properties": {
                    "primary_genres": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "genre_diversity": {"type": "string", "description": "e.g., 'focused', 'diverse', 'eclectic'"},
                    "genre_evolution": {"type": "string", "description": "How genres change across time ranges"}
                }
            },
            "mood_analysis": {
                "type": "object",
                "properties": {
                    "dominant_moods": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "mood_patterns": {"type": "string", "description": "Patterns in mood preferences"},
                    "contextual_listening": {"type": "string", "description": "How mood affects listening choices"}
                }
            }
        },
        "required": [
            "favorite_artists",
            "favorite_songs",
            "last_listened_to",
            "top_played",
            "favorite_tracks_stats",
            "user_profile_summary",
            "playlist_analysis",
            "music_preferences",
            "listening_habits",
            "genres_analysis",
            "mood_analysis"
        ],
        "additionalProperties": False
    }

