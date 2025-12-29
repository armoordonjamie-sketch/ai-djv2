"""Deezer API endpoints for ElevenLabs onboarding agent tools.

These endpoints are called by the ElevenLabs agent via webhook tools
to search music and play previews during the onboarding conversation.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel, Field

from backend_v2.config import ONBOARD_TOOL_SECRET
from backend_v2.integrations.deezer import get_deezer_client
from backend_v2.models.user import User
from backend_v2.auth.dependencies import get_current_user_optional_http

logger = logging.getLogger("ai-dj.deezer-tools")

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ArtistSearchRequest(BaseModel):
    """Request to search for an artist."""
    artist_name: str = Field(..., description="Name of the artist to search for")


class TrackInfo(BaseModel):
    """A simplified track info for agent responses."""
    title: str
    artist: str
    duration_seconds: int = 0
    explicit: bool = False
    # Note: preview_url and album_cover excluded to keep response concise for LLM


class ArtistSearchResponse(BaseModel):
    """Response with artist info and top tracks.
    
    Kept concise to avoid LLM parsing issues with long URLs.
    """
    found: bool
    artist_name: Optional[str] = None
    artist_id: Optional[int] = None
    fan_count: int = 0
    top_tracks: List[TrackInfo] = []



class RelatedArtistsRequest(BaseModel):
    """Request to get related artists."""
    artist_id: Optional[int] = Field(None, description="Deezer artist ID")
    artist_name: Optional[str] = Field(None, description="Artist name (if ID not known)")


class RelatedArtistInfo(BaseModel):
    """A related artist."""
    name: str
    id: int
    fan_count: int = 0


class RelatedArtistsResponse(BaseModel):
    """Response with related artists."""
    found: bool
    artist_names: List[str] = []
    artists: List[RelatedArtistInfo] = []


class TrackSearchRequest(BaseModel):
    """Request to search for tracks."""
    query: str = Field(..., description="Search query (supports artist:, track:, bpm_min:, etc)")
    limit: int = Field(default=5, ge=1, le=20)


class TrackSearchResponse(BaseModel):
    """Response with matching tracks."""
    found: bool
    tracks: List[TrackInfo] = []


# =============================================================================
# Helper Functions
# =============================================================================

def _verify_secret(x_onboard_secret: Optional[str]) -> None:
    """Verify the onboard tool secret."""
    if not ONBOARD_TOOL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboard tool secret not configured",
        )
    
    if x_onboard_secret != ONBOARD_TOOL_SECRET:
        logger.warning("Invalid onboard secret in Deezer tool request")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid onboard secret",
        )


def _track_to_info(track: dict) -> TrackInfo:
    """Convert Deezer track to TrackInfo (simplified for agent responses)."""
    artist = track.get("artist")
    if isinstance(artist, dict):
        artist_name = artist.get("name", "Unknown")
    else:
        artist_name = artist or "Unknown"
    
    return TrackInfo(
        title=track.get("title_short") or track.get("title", "Unknown"),
        artist=artist_name,
        duration_seconds=track.get("duration", 0),
        explicit=track.get("explicit", False),
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/artist-search", response_model=ArtistSearchResponse)
async def search_artist_music(
    request: ArtistSearchRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Search for an artist and get their top tracks.
    
    Called by ElevenLabs agent when user mentions an artist.
    Returns artist info and top 5 tracks with preview URLs.
    """
    _verify_secret(x_onboard_secret)
    
    logger.info(f"Agent searching for artist: {request.artist_name}")
    
    client = get_deezer_client()
    artist = await client.search_artist(request.artist_name)
    
    if not artist:
        return ArtistSearchResponse(found=False)
    
    # Get top tracks
    tracks = await client.get_artist_top_tracks(artist["id"], limit=5)
    
    return ArtistSearchResponse(
        found=True,
        artist_name=artist["name"],
        artist_id=artist["id"],
        fan_count=artist.get("nb_fan", 0),
        top_tracks=[_track_to_info(t) for t in tracks],
    )


@router.post("/related-artists", response_model=RelatedArtistsResponse)
async def get_related_artists(
    request: RelatedArtistsRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Get artists related to a given artist.
    
    Called by ElevenLabs agent when user wants to explore similar music.
    """
    _verify_secret(x_onboard_secret)
    
    logger.info(f"Agent getting related artists for ID: {request.artist_id}, Name: {request.artist_name}")
    
    client = get_deezer_client()
    artist_id = request.artist_id

    # If only name provided, find the ID first
    if not artist_id and request.artist_name:
        logger.info(f"Searching ID for artist: {request.artist_name}")
        search_result = await client.search_artist(request.artist_name)
        if search_result:
            artist_id = search_result["id"]
            logger.info(f"Found artist ID {artist_id} for {request.artist_name}")
        else:
            logger.warning(f"Could not find artist: {request.artist_name}")
            return RelatedArtistsResponse(found=False)
            
    if not artist_id:
        # No ID provided and search failed or wasn't attempted
        logger.warning("No artist_id or valid artist_name provided")
        return RelatedArtistsResponse(found=False)

    artists = await client.get_related_artists(artist_id, limit=5)
    
    if not artists:
        return RelatedArtistsResponse(found=False)
    
    return RelatedArtistsResponse(
        found=True,
        artist_names=[a["name"] for a in artists],
        artists=[
            RelatedArtistInfo(
                name=a["name"],
                id=a["id"],
                fan_count=a.get("nb_fan", 0),
            )
            for a in artists
        ],
    )


@router.post("/track-search", response_model=TrackSearchResponse)
async def search_tracks(
    request: TrackSearchRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Search for tracks with optional advanced filters.
    
    Supports Deezer advanced search:
    - artist:"name" - specific artist
    - track:"name" - specific track  
    - bpm_min:120, bpm_max:180 - BPM range
    - dur_min:180, dur_max:300 - duration in seconds
    """
    _verify_secret(x_onboard_secret)
    
    logger.info(f"Agent searching tracks: {request.query}")
    
    client = get_deezer_client()
    tracks = await client.search_tracks(request.query, limit=request.limit)
    
    if not tracks:
        return TrackSearchResponse(found=False)
    
    return TrackSearchResponse(
        found=True,
        tracks=[_track_to_info(t) for t in tracks],
    )


# =============================================================================
# Audio Preview Playback
# =============================================================================

class PlayPreviewRequest(BaseModel):
    """Request to play a song preview.
    
    Accepts EITHER:
    - artist_name + track_title (preferred - we search Deezer)
    - preview_url (legacy - we use the URL directly)
    """
    artist_name: Optional[str] = Field(None, description="Artist name")
    track_title: Optional[str] = Field(None, description="Track title to play")
    preview_url: Optional[str] = Field(None, description="Direct Deezer preview URL (legacy)")
    duration_seconds: int = Field(default=5, ge=1, le=30, description="How many seconds to play (1-30)")


class PlayPreviewResponse(BaseModel):
    """Response confirming track was found.
    
    Note: ElevenLabs webhook tools cannot actually play audio.
    This just confirms the track exists so the agent can discuss it.
    """
    played: bool
    track_title: Optional[str] = None
    artist_name: Optional[str] = None
    preview_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


@router.post("/play-preview", response_model=PlayPreviewResponse)
async def play_song_preview(
    request: PlayPreviewRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
    current_user: Optional[User] = Depends(get_current_user_optional_http),
):
    """Play a song preview through the ElevenLabs agent.
    
    Accepts either artist_name+track_title (preferred) or preview_url (legacy).
    Searches Deezer and fetches the preview MP3 as base64 audio.
    
    Auth: Requires either X-Onboard-Secret (Agent) or authenticated session (User).
    """
    if not current_user:
        _verify_secret(x_onboard_secret)
    
    logger.info(f"Agent playing preview: {request.track_title} by {request.artist_name}")
    
    # Determine which mode we're in
    use_direct_url = bool(request.preview_url and not request.track_title)
    
    try:
        import httpx
        import base64
        
        preview_url = None
        track_title = request.track_title
        artist_name = request.artist_name
        
        if use_direct_url:
            # Legacy mode: use preview_url directly
            preview_url = request.preview_url
            logger.info(f"Using direct preview URL: {preview_url[:60]}...")
        else:
            # New mode: search for track by artist+title
            if not artist_name or not track_title:
                return PlayPreviewResponse(
                    played=False,
                    error="Need either preview_url OR artist_name+track_title"
                )
            
            client = get_deezer_client()
            query = f'artist:"{artist_name}" track:"{track_title}"'
            tracks = await client.search_tracks(query, limit=1, strict=True)
            
            # Fallback to looser search if strict finds nothing
            if not tracks:
                query = f"{artist_name} {track_title}"
                tracks = await client.search_tracks(query, limit=1)
            
            if not tracks:
                logger.warning(f"Track not found: {artist_name} - {track_title}")
                return PlayPreviewResponse(
                    played=False,
                    track_title=track_title,
                    artist_name=artist_name,
                    error="Track not found on Deezer"
                )
            
            track = tracks[0]
            preview_url = track.get("preview")
            track_title = track.get("title", track_title)
        
        if not preview_url:
            logger.warning(f"No preview URL for: {track_title}")
            return PlayPreviewResponse(
                played=False,
                track_title=track_title,
                artist_name=artist_name,
                error="No preview available for this track"
            )
        
        if not preview_url:
            logger.warning(f"No preview URL for: {track_title}")
            return PlayPreviewResponse(
                played=False,
                track_title=track_title,
                artist_name=artist_name,
                error="No preview available for this track"
            )
        
        logger.info(f"Found preview URL: {preview_url[:60]}...")
        
        # Note: We don't download the audio anymore because:
        # 1. ElevenLabs webhook tools have a 256KB response limit
        # 2. ElevenLabs doesn't currently support playing audio from webhook responses
        # 3. We will implement client-side playback in the frontend next
        
        return PlayPreviewResponse(
            played=True,
            track_title=track_title,
            artist_name=artist_name,
            preview_url=preview_url,
            duration_seconds=track.get("duration", 0),
            message="Preview found. Use client-side tool to play."
        )
            
    except Exception as e:
        logger.error(f"Failed to play preview: {e}")
        return PlayPreviewResponse(
            played=False,
            track_title=request.track_title,
            artist_name=request.artist_name,
            error=str(e)
        )

