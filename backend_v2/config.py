"""Configuration for AI-DJ Backend v2.

All configuration is loaded from environment variables via python-dotenv.
See .env.example for available options.
"""
import os
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()  # Load from .env file


# =============================================================================
# Database
# =============================================================================
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/persistence.db")
# Legacy path for backwards compatibility
DB_PATH: str = os.getenv("DB_PATH", "data/persistence.db")


# =============================================================================
# JWT Authentication
# =============================================================================
JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
ACCESS_TOKEN_EXPIRES_MIN: int = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "30"))
REFRESH_TOKEN_EXPIRES_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "7"))


# =============================================================================
# Cookie Settings
# =============================================================================
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "Lax")
COOKIE_DOMAIN: Optional[str] = os.getenv("COOKIE_DOMAIN") or None


# =============================================================================
# Security
# =============================================================================
CSRF_ENABLED: bool = os.getenv("CSRF_ENABLED", "true").lower() == "true"
WS_ALLOW_QUERY_TOKEN: bool = os.getenv("WS_ALLOW_QUERY_TOKEN", "false").lower() == "true"


# =============================================================================
# Session Limits
# =============================================================================
MAX_SESSIONS_PER_USER: int = int(os.getenv("MAX_SESSIONS_PER_USER", "1"))
MAX_SESSIONS_TOTAL: int = int(os.getenv("MAX_SESSIONS_TOTAL", "200"))


# =============================================================================
# CORS
# =============================================================================
_cors_origins_raw: str = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS: List[str] = [
    origin.strip() 
    for origin in _cors_origins_raw.split(",") 
    if origin.strip()
]
# Dev fallback: if no origins specified, allow common dev origins
# NOTE: In production, set CORS_ALLOWED_ORIGINS env var to include production frontend URL
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173", 
        "http://localhost:3000", 
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://app.jamiearmoordon.co.uk",  # Production frontend
        "https://jamify.jamiearmoordon.co.uk",  # API domain (same-origin calls)
    ]


# =============================================================================
# Demo Mode
# =============================================================================
ENABLE_DEMO_MODE: bool = os.getenv("ENABLE_DEMO_MODE", "true").lower() == "true"


# =============================================================================
# External APIs
# =============================================================================
OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
ELEVENLABS_API_KEY: Optional[str] = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "aD6riP1btT197c6dACmy")
ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

# ElevenLabs Onboarding Agent (Voice Onboarding)
ELEVENLABS_ONBOARD_AGENT_ID: Optional[str] = os.getenv("ELEVENLABS_ONBOARD_AGENT_ID")
ELEVENLABS_ONBOARD_TOOL_ID: Optional[str] = os.getenv("ELEVENLABS_ONBOARD_TOOL_ID")
ELEVENLABS_CUSTOM_LLM_SECRET: Optional[str] = os.getenv("ELEVENLABS_CUSTOM_LLM_SECRET")
ONBOARD_TOOL_SECRET: Optional[str] = os.getenv("ONBOARD_TOOL_SECRET")
OPENROUTER_ONBOARD_MODEL: str = os.getenv("OPENROUTER_ONBOARD_MODEL", "google/gemini-2.5-flash-lite")


# =============================================================================
# Music Metadata (ListenBrainz / MusicBrainz)
# =============================================================================
LISTENBRAINZ_USER_TOKEN: Optional[str] = os.getenv("LISTENBRAINZ_USER_TOKEN")
MUSICBRAINZ_CONTACT_EMAIL: Optional[str] = os.getenv("MUSICBRAINZ_CONTACT_EMAIL")
MUSICBRAINZ_RATE_LIMIT: float = float(os.getenv("MUSICBRAINZ_RATE_LIMIT", "1"))


# =============================================================================
# Apify (for Apple Music scraping, no Apple Dev account needed)
# =============================================================================
APIFY_API_TOKEN: Optional[str] = os.getenv("APIFY_API_TOKEN")


# =============================================================================
# Paths
# =============================================================================
SONG_CACHE_DIR: str = os.getenv("SONG_CACHE_DIR", "data/cache/songs")
SEGMENT_DIR: str = os.getenv("SEGMENT_DIR", "data/segments")
TTS_DIR: str = os.getenv("TTS_DIR", "data/tts")
USER_CONTEXT_FILE: str = os.getenv("USER_CONTEXT_FILE", "data/user_context.txt")
CACHE_MAX_BYTES: int = 50_000_000_000  # 50GB


# =============================================================================
# Agent Configuration
# =============================================================================
THINKING_BUDGETS = {
    "track_selector": int(os.getenv("THINKING_BUDGET_TRACK", "2000")),
    "transition_planner": int(os.getenv("THINKING_BUDGET_TRANSITION", "1500")),
    "speech_writer": int(os.getenv("THINKING_BUDGET_SPEECH", "3500")),
}
# Individual constants for direct import
THINKING_BUDGET_TRACK: int = THINKING_BUDGETS["track_selector"]
THINKING_BUDGET_TRANSITION: int = THINKING_BUDGETS["transition_planner"]
THINKING_BUDGET_SPEECH: int = THINKING_BUDGETS["speech_writer"]



# =============================================================================
# Audio Processing
# =============================================================================
TARGET_LUFS: float = float(os.getenv("TARGET_LUFS", "-14.0"))
BASS_CROSSOVER_FREQ: float = float(os.getenv("BASS_CROSSOVER_FREQ", "250"))
TTS_DUCK_VOLUME: float = float(os.getenv("TTS_DUCK_VOLUME", "0.45"))


# =============================================================================
# Transition Settings
# =============================================================================
TRANSITION_TYPES_ENABLED = os.getenv("TRANSITION_TYPES", "all").split(",")
TRANSITION_GUIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "docs", 
    "transition-field-guide.md"
)


# =============================================================================
# Hard Constraints (Persona Music Rules)
# =============================================================================
# Songs below these thresholds are HARD REJECTED when features are known
DEFAULT_MIN_TEMPO_BPM: int = int(os.getenv("DEFAULT_MIN_TEMPO_BPM", "90"))
DEFAULT_MIN_ENERGY: float = float(os.getenv("DEFAULT_MIN_ENERGY", "0.30"))
DEFAULT_MIN_DANCEABILITY: float = float(os.getenv("DEFAULT_MIN_DANCEABILITY", "0.20"))

# Ballad/slow song genre/tag denylist (hard reject if any match)
BALLAD_GENRE_DENYLIST: List[str] = [
    "ballad", "lullaby", "ambient", "drone", "meditation",
    "sleep", "relaxation", "new age", "spa", "yoga",
]

# Whether to hard-reject songs with unknown features (False = allow but deprioritize)
REJECT_UNKNOWN_FEATURES: bool = os.getenv("REJECT_UNKNOWN_FEATURES", "false").lower() == "true"

# Score penalty for songs with unknown features (if not hard-rejected)
UNKNOWN_FEATURES_PENALTY: float = float(os.getenv("UNKNOWN_FEATURES_PENALTY", "0.2"))


# =============================================================================
# Download Safety (Denylist Patterns)
# =============================================================================
DOWNLOAD_DENYLIST_PATTERNS: List[str] = [
    r"\bfull\s+album\b",
    r"\balbum\s+(version|mix)\b",
    r"\b(1|2|3|one|two|three)\s+hour\b",
    r"\blive\s+(set|session|concert|performance)\b",
    r"\bmix\s*(tape|compilation)?\b",
    r"\bsped\s+up\b",
    r"\bslowed\s*(down|and\s+reverb)?\b",
    r"\bnightcore\b",
    r"\b8d\s*(audio)?\b",
    r"\bremix\s+compilation\b",
    r"\bplaylist\b",
    r"\bcomplete\s+(discography|collection)\b",
    r"\bkaraoke\b",
    r"\binstrumental\s+version\b",
]

# Max concurrent downloads per user (prevents resource exhaustion)
MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))

# Download timeout (seconds)
DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "120"))


# =============================================================================
# Download Pipeline
# =============================================================================
SPONSORBLOCK_API_URL: str = os.getenv("SPONSORBLOCK_API_URL", "https://sponsor.ajay.app")
YTDLP_PATH: str = os.getenv("YTDLP_PATH", "yt-dlp")
SONG_MAX_DURATION_SEC: int = int(os.getenv("SONG_MAX_DURATION_SEC", "600"))
SPONSORBLOCK_MAX_TRIM_RATIO: float = float(os.getenv("SPONSORBLOCK_MAX_TRIM_RATIO", "0.20"))
DOWNLOAD_MAX_RETRIES: int = int(os.getenv("DOWNLOAD_MAX_RETRIES", "2"))


# =============================================================================
# Streaming
# =============================================================================
STREAM_MP3_BITRATE: str = os.getenv("STREAM_MP3_BITRATE", "192k")
STREAM_SAMPLE_RATE: int = int(os.getenv("STREAM_SAMPLE_RATE", "44100"))
STREAM_CHANNELS: int = int(os.getenv("STREAM_CHANNELS", "2"))
ENABLE_ICY_METADATA: bool = os.getenv("ENABLE_ICY_METADATA", "false").lower() == "true"
STREAM_CLIENT_QUEUE_SIZE: int = int(os.getenv("STREAM_CLIENT_QUEUE_SIZE", "500"))
ICY_METAINT: int = int(os.getenv("ICY_METAINT", "16000"))

# Stream Startup Behavior
# "defer" = don't emit audio until first real segment is ready (preferred)
# "bounded" = emit bounded silence to keep connection alive
STREAM_STARTUP_MODE: str = os.getenv("STREAM_STARTUP_MODE", "defer")
MAX_SILENCE_AHEAD_SEC: float = float(os.getenv("MAX_SILENCE_AHEAD_SEC", "3.0"))
MAX_BUFFERED_AUDIO_SEC: float = float(os.getenv("MAX_BUFFERED_AUDIO_SEC", "20.0"))
STREAM_STARTUP_TIMEOUT_SEC: int = int(os.getenv("STREAM_STARTUP_TIMEOUT_SEC", "60"))


# =============================================================================
# Frontend Serving (Prod-like mode)
# =============================================================================
SERVE_FRONTEND: bool = os.getenv("SERVE_FRONTEND", "false").lower() == "true"
FRONTEND_DIST_DIR: str = os.getenv(
    "FRONTEND_DIST_DIR", 
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
)
APP_PORT: int = int(os.getenv("APP_PORT", "5173" if SERVE_FRONTEND else "8000"))

# =============================================================================
# Validation
# =============================================================================
def validate_config() -> List[str]:
    """Validate configuration and return list of warnings."""
    warnings = []
    
    if not JWT_SECRET:
        warnings.append("JWT_SECRET not set - authentication will not work!")
    
    if not OPENROUTER_API_KEY:
        warnings.append("OPENROUTER_API_KEY not set - LLM features disabled")
    
    if not ELEVENLABS_API_KEY:
        warnings.append("ELEVENLABS_API_KEY not set - TTS features disabled")
    
    if not MUSICBRAINZ_CONTACT_EMAIL:
        warnings.append("MUSICBRAINZ_CONTACT_EMAIL not set - may be rate limited")
    
    # Check if CORS_ALLOWED_ORIGINS env var is set
    _cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not _cors_env.strip():
        warnings.append(
            "CORS_ALLOWED_ORIGINS not set - using fallback origins. "
            "In production, set CORS_ALLOWED_ORIGINS to include your frontend URL(s)"
        )
    
    return warnings
