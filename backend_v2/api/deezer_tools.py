"""Deezer API endpoints for ElevenLabs onboarding agent tools.

These endpoints are called by the ElevenLabs agent via webhook tools
to search music and play previews during the onboarding conversation.
"""
import logging
import random
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from backend_v2.config import DEEZER_API_BASE, ONBOARD_TOOL_SECRET
from backend_v2.models.user import User
from backend_v2.models.spotify_context import SpotifyUserContext
from backend_v2.auth.dependencies import get_current_user_optional_http
from backend_v2.integrations.deezer import get_deezer_client
from backend_v2.db.session import get_async_session

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


class MoodSearchRequest(BaseModel):
    """Request to search for tracks matching a mood."""
    mood: str = Field(..., description="The mood/vibe: chill, energetic, melancholic, happy, romantic, angry, focused")
    genres: Optional[List[str]] = Field(default=None, description="Optional genre hints")


class EraSearchRequest(BaseModel):
    """Request to get tracks from a specific era."""
    era: str = Field(..., description="Decade or era: 70s, 80s, 90s, 2000s, 2010s, recent, classic")
    genre: Optional[str] = Field(default=None, description="Optional genre filter")


class GenreExploreRequest(BaseModel):
    """Request to explore a specific genre."""
    genre: str = Field(..., description="Genre to explore")
    subgenre: Optional[str] = Field(default=None, description="Optional subgenre")


class VibeCheckRequest(BaseModel):
    """Request for contrasting tracks for quick preference checking."""
    dimension: str = Field(..., description="What to test: energy, era, vocal, mood")


class VibeCheckResponse(BaseModel):
    """Response with a pair of contrasting tracks."""
    pair_name: str
    track_a: TrackInfo
    track_b: TrackInfo
    question: str


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
    
    async with httpx.AsyncClient() as client:
        # Search for the artist
        artist_search_response = await client.get(
            f"{DEEZER_API_BASE}/search/artist",
            params={"q": request.artist_name, "limit": 1}
        )
        artist_data = artist_search_response.json().get("data")
        
        if not artist_data:
            return ArtistSearchResponse(found=False)
        
        artist = artist_data[0]
        
        # Get top tracks
        top_tracks_response = await client.get(
            f"{DEEZER_API_BASE}/artist/{artist['id']}/top",
            params={"limit": 5}
        )
        tracks = top_tracks_response.json().get("data", [])
        
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
    
    artist_id = request.artist_id

    async with httpx.AsyncClient() as client:
        # If only name provided, find the ID first
        if not artist_id and request.artist_name:
            logger.info(f"Searching ID for artist: {request.artist_name}")
            search_result = await client.get(
                f"{DEEZER_API_BASE}/search/artist",
                params={"q": request.artist_name, "limit": 1}
            )
            search_data = search_result.json().get("data")
            if search_data:
                artist_id = search_data[0]["id"]
                logger.info(f"Found artist ID {artist_id} for {request.artist_name}")
            else:
                logger.warning(f"Could not find artist: {request.artist_name}")
                return RelatedArtistsResponse(found=False)
                
        if not artist_id:
            # No ID provided and search failed or wasn't attempted
            logger.warning("No artist_id or valid artist_name provided")
            return RelatedArtistsResponse(found=False)

        related_artists_response = await client.get(
            f"{DEEZER_API_BASE}/artist/{artist_id}/related",
            params={"limit": 5}
        )
        artists = related_artists_response.json().get("data", [])
        
        if not artists:
            logger.info(f"No related artists found for {artist_id} (name: {request.artist_name}) after all fallback strategies")
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
    
    query = request.query
    limit = request.limit
    
    logger.info(f"Agent searching tracks: query='{query}' limit={limit}")
    
    async with httpx.AsyncClient() as client:
        # Pass query directly to Deezer
        response = await client.get(
            f"{DEEZER_API_BASE}/search",
            params={"q": query, "limit": limit}
        )
        
        if response.status_code != 200:
            logger.error(f"Deezer API error: {response.text}")
            return TrackSearchResponse(found=False)
            
        data = response.json()
        tracks = data.get("data", [])
        
        if not tracks:
            return TrackSearchResponse(found=False)
            
        # Convert to simplified response
        track_infos = [_track_to_info(t) for t in tracks]
        
        return TrackSearchResponse(
            found=True,
            tracks=track_infos
        )


@router.post("/mood-search", response_model=TrackSearchResponse)
async def search_mood_tracks(
    request: MoodSearchRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Search for tracks matching a mood/vibe."""
    _verify_secret(x_onboard_secret)
    
    mood_lower = request.mood.lower()
    logger.info(f"Agent searching mood: '{mood_lower}' (genres={request.genres})")
    
    # Map moods to search terms/playlists
    # We construct a qualified search query for Deezer
    search_term = mood_lower
    
    # Simple mapping of moods to search qualifiers
    mood_map = {
        "chill": "chill relaxed lo-fi",
        "energetic": "energy workout hype",
        "party": "party dance upbeat",
        "focus": "focus study instrumental",
        "melancholic": "sad emotional acoustic",
        "romantic": "love romance r&b",
        "angry": "rock metal intensity",
        "happy": "happy feelgood sunshine"
    }
    
    if mood_lower in mood_map:
        search_term = mood_map[mood_lower]
        
    # Append genre if provided
    if request.genres:
        genre_str = " ".join(request.genres[:2])
        search_term = f"{search_term} {genre_str}"
        
    async with httpx.AsyncClient() as client:
        # Search tracks with this mood context
        response = await client.get(
            f"{DEEZER_API_BASE}/search",
            params={"q": search_term, "limit": 10}  # Fetch more to shuffle
        )
        
        if response.status_code != 200:
            return TrackSearchResponse(found=False)
            
        data = response.json()
        tracks = data.get("data", [])
        
        if not tracks:
            return TrackSearchResponse(found=False)
            
        # Shuffle for variety
        random.shuffle(tracks)
        selected = tracks[:5]
        
        return TrackSearchResponse(
            found=True,
            tracks=[_track_to_info(t) for t in selected]
        )


@router.post("/era-search", response_model=TrackSearchResponse)
async def search_era_tracks(
    request: EraSearchRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Search for tracks from a specific era."""
    _verify_secret(x_onboard_secret)
    
    era = request.era.lower()
    logger.info(f"Agent searching era: '{era}'")
    
    # Parse decades
    year_min = None
    year_max = None
    
    if "70s" in era:
        year_min, year_max = 1970, 1979
    elif "80s" in era:
        year_min, year_max = 1980, 1989
    elif "90s" in era:
        year_min, year_max = 1990, 1999
    elif "2000s" in era or "00s" in era:
        year_min, year_max = 2000, 2009
    elif "2010s" in era or "10s" in era:
        year_min, year_max = 2010, 2019
    elif "recent" in era or "new" in era:
        year_min = 2023
    elif "classic" in era:
        year_max = 1990
        
    query = request.genre if request.genre else "hits"
    
    params = {"q": query, "limit": 20}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DEEZER_API_BASE}/search",
            params=params
        )
        tracks = response.json().get("data", [])
        
        # Filter by year if we have release dates (Deezer doesn't always support date filtering in basic search)
        # Note: Deezer API doesn't have robust year filtering in free tier search, 
        # so we filter client-side if we can, or rely on adding year to query
        
        # Improved strategy: Add qualifers to query
        if year_min and year_max:
            # Try to bias search
            pass 
            # Note: client-side filtering involves fetching album details which is slow.
            # We'll rely on string matching "best of 80s" etc if user input was vague
        
        # If user asked for specific decade, verify/shuffle
        random.shuffle(tracks)
        return TrackSearchResponse(
            found=True,
            tracks=[_track_to_info(t) for t in tracks[:5]]
        )


@router.post("/genre-explore", response_model=TrackSearchResponse)
async def explore_genre(
    request: GenreExploreRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Deep dive into a genre."""
    _verify_secret(x_onboard_secret)
    
    query = f'genre:"{request.genre}"'
    if request.subgenre:
        query += f" {request.subgenre}"
    else:
        query += " best of"
        
    logger.info(f"Agent exploring genre: {query}")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DEEZER_API_BASE}/search",
            params={"q": query, "limit": 10}
        )
        tracks = response.json().get("data", [])
        
        # Remove duplicates/remixes
        unique_tracks = []
        seen = set()
        for t in tracks:
            key = f"{t.get('title')}-{t.get('artist', {}).get('name')}"
            if key not in seen:
                seen.add(key)
                unique_tracks.append(t)
                
        return TrackSearchResponse(
            found=bool(unique_tracks),
            tracks=[_track_to_info(t) for t in unique_tracks[:5]]
        )


@router.post("/vibe-check", response_model=VibeCheckResponse)
async def quick_vibe_check(
    request: VibeCheckRequest,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
):
    """Get a contrasting pair of tracks to check user preference."""
    _verify_secret(x_onboard_secret)
    
    dim = request.dimension.lower()
    
    # Pre-defined pairs for common dimensions
    pairs = {
        "energy": [
            ("chill", "high energy"), 
            ("Pink Floyd", "The Prodigy"),
            ("Billie Eilish", "Skrillex")
        ],
        "era": [
            ("The Beatles", "Drake"),
            ("Queen", "The Weeknd"), 
            ("80s pop", "Hyperpop")
        ],
        "mood": [
            ("Happy", "Sad"),
            ("Party", "Focus")
        ]
    }
    
    # Select search terms
    if dim in pairs:
        choice = random.choice(pairs[dim])
        term_a, term_b = choice
    else:
        term_a, term_b = "Pop", "Metal" # Default fallback
        
    async with httpx.AsyncClient() as client:
        # Fetch A
        resp_a = await client.get(f"{DEEZER_API_BASE}/search", params={"q": term_a, "limit": 1})
        # Fetch B
        resp_b = await client.get(f"{DEEZER_API_BASE}/search", params={"q": term_b, "limit": 1})
        
        track_a = resp_a.json().get("data", [])
        track_b = resp_b.json().get("data", [])
        
        if not track_a or not track_b:
            raise HTTPException(status_code=404, detail="Could not find vibe check tracks")
            
        return VibeCheckResponse(
            pair_name=dim,
            track_a=_track_to_info(track_a[0]),
            track_b=_track_to_info(track_b[0]),
            question=f"Do you prefer {term_a} or {term_b}?"
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
    artwork_url: Optional[str] = None  # Album artwork for UI display
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
        preview_url = None
        track_title = request.track_title
        artist_name = request.artist_name
        artwork_url = None
        duration_seconds = 0
        track = None
        
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
            duration_seconds = track.get("duration", 0)
            
            # Extract artwork URL from album
            album = track.get("album", {})
            if album:
                # Prefer larger cover sizes
                artwork_url = album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or album.get("cover")
        
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
            artwork_url=artwork_url,
            duration_seconds=duration_seconds,
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


# =============================================================================
# Spotify Context Tool
# =============================================================================

class SpotifyContextRequest(BaseModel):
    """Request to get user's Spotify listening data."""
    user_id: str = Field(..., description="User ID to fetch Spotify data for")


class SpotifyContextResponse(BaseModel):
    """Response with user's Spotify listening data."""
    has_spotify: bool = Field(..., description="Whether user has connected Spotify")
    top_artists: List[str] = Field(default_factory=list, description="Top artists from Spotify")
    top_tracks: List[Dict[str, Any]] = Field(default_factory=list, description="Top tracks with play stats")
    favorite_genres: List[str] = Field(default_factory=list, description="Favorite genres from Spotify analysis")
    listening_summary: Optional[str] = Field(None, description="Natural language summary of listening habits")


@router.post("/spotify-context", response_model=SpotifyContextResponse)
async def get_spotify_context(
    request: SpotifyContextRequest,
    x_onboard_secret: str = Header(..., alias="X-Onboard-Secret"),
    db: AsyncSession = Depends(get_async_session),
):
    """Get user's Spotify listening data for personalized onboarding.
    
    This endpoint is called by the ElevenLabs agent to fetch the user's
    Spotify data if they've connected their account. Returns their top
    artists, tracks with play counts, and music preferences.
    """
    # Validate secret
    if x_onboard_secret != ONBOARD_TOOL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid onboarding tool secret"
        )
    
    try:
        # Check if user has connected Spotify
        stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == request.user_id)
        result = await db.execute(stmt)
        spotify_context = result.scalar_one_or_none()
        
        if not spotify_context:
            logger.info(f"No Spotify data for user {request.user_id}")
            return SpotifyContextResponse(has_spotify=False)
        
        logger.info(f"Found Spotify data for user {request.user_id}")
        logger.info(f"Raw top_tracks_json length: {len(spotify_context.top_tracks_json) if spotify_context.top_tracks_json else 'None'}")
        logger.info(f"Raw top_tracks_json preview: {spotify_context.top_tracks_json[:300] if spotify_context.top_tracks_json else 'None'}")
        logger.info(f"Raw top_artists_json length: {len(spotify_context.top_artists_json) if spotify_context.top_artists_json else 'None'}")
        logger.info(f"Raw top_artists_json preview: {spotify_context.top_artists_json[:200] if spotify_context.top_artists_json else 'None'}")
        logger.info(f"Enriched favorite_tracks_stats length: {len(spotify_context.favorite_tracks_with_stats_json) if spotify_context.favorite_tracks_with_stats_json else 'None'}")

        # Extract top artists (try all time ranges in preference order)
        top_artists = []
        try:
            if spotify_context.top_artists_json:
                artists_data = json.loads(spotify_context.top_artists_json)
                
                # Try terms in order of preference
                for term in ["medium_term", "short_term", "long_term"]:
                    term_artists = artists_data.get(term, [])
                    if term_artists:
                        logger.info(f"Using {term} artists (count: {len(term_artists)})")
                        for artist in term_artists[:5]:
                            if isinstance(artist, dict) and artist.get("name"):
                                top_artists.append(artist["name"])
                        break
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing top_artists_json: {e}")
        
        # Extract top tracks with stats
        top_tracks = []
        try:
            if spotify_context.favorite_tracks_with_stats_json:
                tracks_data = json.loads(spotify_context.favorite_tracks_with_stats_json)
                # Get top 5 tracks with their play stats
                for track in tracks_data[:5]:
                    if isinstance(track, dict):
                        time_range_label = {
                            "short_term": "last month",
                            "medium_term": "last 6 months",
                            "long_term": "all time"
                        }.get(track.get("time_range", ""), "recently")
                        
                        top_tracks.append({
                            "title": track.get("title"),
                            "artist": track.get("artist"),
                            "rank": track.get("rank"),
                            "time_range": time_range_label
                        })
            
            # Fallback to raw data if enriched data is missing
            if not top_tracks and spotify_context.top_tracks_json:
                try:
                    tracks_data = json.loads(spotify_context.top_tracks_json)
                    # Raw data structure: {"short_term": [...], "medium_term": [...], "long_term": [...]}
                    
                    # Try terms in order of preference
                    found_tracks = []
                    for term in ["medium_term", "short_term", "long_term"]:
                        term_tracks = tracks_data.get(term, [])
                        if term_tracks:
                            logger.info(f"Using {term} tracks for fallback (count: {len(term_tracks)})")
                            found_tracks = term_tracks
                            break
                    
                    for idx, track in enumerate(found_tracks[:5]):
                        if isinstance(track, dict):
                            # Spotify raw track object has 'name' and 'artists' list
                            artist_name = "Unknown"
                            if track.get("artists") and len(track["artists"]) > 0:
                                artist_name = track["artists"][0].get("name", "Unknown")
                                
                            top_tracks.append({
                                "title": track.get("name"),
                                "artist": artist_name,
                                "rank": idx + 1,
                                "time_range": "last 6 months"
                            })
                            
                    # If top_artists is empty, extract from top_tracks
                    if not top_artists and top_tracks:
                        logger.info("Extracting top artists from top tracks")
                        seen_artists = set()
                        for t in top_tracks:
                            artist = t.get("artist")
                            if artist and artist != "Unknown" and artist not in seen_artists:
                                top_artists.append(artist)
                                seen_artists.add(artist)
                                
                except Exception as e:
                    logger.error(f"Error parsing raw top tracks: {e}")
        except json.JSONDecodeError:
            pass
        
        # Extract favorite genres
        favorite_genres = []
        try:
            if spotify_context.genres_analysis_json:
                genres_analysis = json.loads(spotify_context.genres_analysis_json)
                primary_genres = genres_analysis.get("primary_genres", [])
                # Handle both list and comma-separated string formats
                if isinstance(primary_genres, str):
                    # Parse comma-separated string: "UK Rap, Grime, Electronic"
                    favorite_genres = [g.strip() for g in primary_genres.split(",") if g.strip()][:5]
                elif isinstance(primary_genres, list):
                    favorite_genres = primary_genres[:5]
        except json.JSONDecodeError:
            pass
        
        # Build listening summary
        listening_summary = None
        try:
            if spotify_context.listening_habits_json:
                listening_habits = json.loads(spotify_context.listening_habits_json)
                listening_frequency = listening_habits.get("listening_frequency", "")
                if listening_frequency:
                    listening_summary = f"This user {listening_frequency}. "
            
            if top_artists:
                listening_summary = (listening_summary or "") + f"Top artists: {', '.join(top_artists[:3])}. "
            
            if favorite_genres:
                listening_summary = (listening_summary or "") + f"Favorite genres: {', '.join(favorite_genres[:3])}."
        except json.JSONDecodeError:
            pass
        
        return SpotifyContextResponse(
            has_spotify=True,
            top_artists=top_artists,
            top_tracks=top_tracks,
            favorite_genres=favorite_genres,
            listening_summary=listening_summary
        )
        
    except Exception as e:
        logger.error(f"Failed to fetch Spotify context: {e}")
        # Return empty response rather than failing
        return SpotifyContextResponse(has_spotify=False)

