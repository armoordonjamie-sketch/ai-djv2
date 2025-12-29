"""Orchestration agents for AI DJ pipeline.

These agents use PreferenceBundle for personalization and call
external APIs (OpenRouter for LLM, ElevenLabs for TTS).

Evidence: Implementing Phase 4 of implementation_plan.md
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend_v2.services.preference_bundle import (
    PreferenceBundle,
    HistoryItem,
    build_preference_bundle,
    get_bundle_cache,
    get_scored_candidates,
    score_candidate,
)
from backend_v2.services.persona import (
    DJPersona,
    get_compiled_persona,
)
from backend_v2.integrations.openrouter import get_openrouter_client, store_llm_trace
from backend_v2.integrations.elevenlabs import get_elevenlabs_client

# NEW: Import catalog and acquisition modules
from backend_v2.catalog.selector import select_diverse_track
from backend_v2.catalog.providers import CatalogTrack, get_deezer_provider
from backend_v2.services.acquisition import get_acquisition_service
from backend_v2.models.track_intent import TrackIntent, TrackIntentStatus
from backend_v2.monitoring.metrics import get_metrics
from backend_v2.orchestration.state import DJState, add_decision_step
from backend_v2.models.existing import Song
from backend_v2.utils.time import utc_isoformat, utc_now

logger = logging.getLogger("ai-dj.agents")

# Per-user persona cache
_persona_cache: Dict[str, DJPersona] = {}


def get_persona_for_user(bundle: PreferenceBundle) -> DJPersona:
    """Get or compile persona for a user.
    
    Caches persona per user_id and handles cooldown advancement.
    """
    global _persona_cache
    
    user_id = bundle.user_id
    
    if user_id not in _persona_cache:
        _persona_cache[user_id] = get_compiled_persona(bundle)
        logger.info(f"Compiled persona for user {user_id}")
    
    return _persona_cache[user_id]


def advance_persona_cooldowns(bundle: PreferenceBundle, speech_text: str):
    """Advance persona cooldowns after speech generation.
    
    Call this after generating speech to:
    1. Record which roast topics were used
    2. Advance all cooldown timers
    """
    persona = get_persona_for_user(bundle)
    persona.record_speech(speech_text)
    persona.advance_segment()


# =============================================================================
# Song Acquisition (Download if not in cache)
# =============================================================================

# Concurrency guard: tracks in-progress downloads to prevent duplicates
_download_locks: Dict[str, asyncio.Lock] = {}
_download_locks_guard = asyncio.Lock()


def _normalize_query(artist: str, title: str) -> str:
    """Normalize artist + title for deduplication."""
    return f"{artist.strip().lower()} - {title.strip().lower()}"


def _validate_download_query(artist: str, title: str) -> Tuple[bool, Optional[str]]:
    """Validate that artist/title are safe to download.
    
    Returns:
        (is_valid, rejection_reason)
    """
    import re
    from backend_v2.config import DOWNLOAD_DENYLIST_PATTERNS
    
    # Must have both artist and title
    if not artist or not artist.strip():
        return False, "empty artist"
    if not title or not title.strip():
        return False, "empty title"
    
    # Both must be at least 2 chars
    if len(artist.strip()) < 2:
        return False, "artist too short"
    if len(title.strip()) < 2:
        return False, "title too short"
    
    # Check query against denylist
    query = f"{artist} - {title}"
    for pattern in DOWNLOAD_DENYLIST_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return False, f"matches denylist: {pattern}"
    
    return True, None


def _extract_features_from_song(song: Song) -> Optional[Dict[str, Any]]:
    """Build a features dict from a Song model if available."""
    if not song or not song.features:
        return None
    return {
        "energy": song.features.energy,
        "valence": song.features.valence,
        "tempo": song.features.tempo,
        "key": song.features.key,
        "mode": song.features.mode,
        "danceability": song.features.danceability,
        "acousticness": song.features.acousticness,
        "instrumentalness": song.features.instrumentalness,
    }


async def acquire_song_by_name(
    db: AsyncSession,
    artist: str,
    title: str,
    target_uuid: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Acquire a song by name - downloads if not in cache.
    
    This is called when the AI suggests a specific song that may not
    be in the local library. It searches YouTube and downloads if needed.
    
    Safety features:
    - Validates artist/title format
    - Rejects denylist patterns (albums, mixes, etc.)
    - Concurrency guard prevents duplicate downloads
    - Timeout prevents stalling
    
    Args:
        db: Database session
        artist: Artist name
        title: Song title
        target_uuid: Optional UUID to use when storing
        timeout_seconds: Max time for download (uses config default if None)
        
    Returns:
        Song dict with uuid, title, artist, local_path, or None if failed
    """
    import asyncio
    from backend_v2.tools.song_downloader import get_song_downloader
    from backend_v2.config import DOWNLOAD_TIMEOUT_SECONDS
    
    # Validate inputs
    is_valid, rejection_reason = _validate_download_query(artist, title)
    if not is_valid:
        logger.warning(f"Download query rejected: {artist} - {title} ({rejection_reason})")
        return None
    
    # First check if we already have this song
    result = await db.execute(
        select(Song).options(selectinload(Song.features)).where(
            Song.artist.ilike(f"%{artist}%"),
            Song.title.ilike(f"%{title}%")
        )
    )
    existing = result.scalars().first()
    
    if existing and existing.local_path:
        import os
        if os.path.exists(existing.local_path):
            logger.info(f"Song already cached: {artist} - {title}")
            features = _extract_features_from_song(existing)
            return {
                "uuid": existing.uuid,
                "title": existing.title,
                "artist": existing.artist,
                "local_path": existing.local_path,
                "duration_sec": existing.duration_sec,
                "artwork_url": existing.artwork_url,
                "features": features,
            }
    
    # Concurrency guard: prevent duplicate simultaneous downloads
    normalized = _normalize_query(artist, title)
    
    async with _download_locks_guard:
        if normalized not in _download_locks:
            _download_locks[normalized] = asyncio.Lock()
        lock = _download_locks[normalized]
    
    # Try to acquire lock (don't wait forever)
    try:
        acquired = await asyncio.wait_for(lock.acquire(), timeout=1.0)
    except asyncio.TimeoutError:
        logger.info(f"Download already in progress: {artist} - {title}")
        return None
    
    try:
        # Re-check cache after acquiring lock (another task may have completed)
        result = await db.execute(
            select(Song).options(selectinload(Song.features)).where(
                Song.artist.ilike(f"%{artist}%"),
                Song.title.ilike(f"%{title}%")
            )
        )
        existing = result.scalars().first()
        
        if existing and existing.local_path:
            import os
            if os.path.exists(existing.local_path):
                features = _extract_features_from_song(existing)
                return {
                    "uuid": existing.uuid,
                    "title": existing.title,
                    "artist": existing.artist,
                    "local_path": existing.local_path,
                    "duration_sec": existing.duration_sec,
                    "features": features,
                }
        
        # Download the song with timeout
        logger.info(f"Downloading song: {artist} - {title}")
        timeout = timeout_seconds or DOWNLOAD_TIMEOUT_SECONDS
        
        try:
            downloader = get_song_downloader()
            query = f"{artist} - {title} official audio"
            
            result = await asyncio.wait_for(
                downloader.download_song(
                    query=query,
                    artist=artist,
                    title=title,
                    target_uuid=target_uuid,
                    skip_db_storage=False,
                ),
                timeout=timeout,
            )
            
            if result:
                logger.info(f"Successfully acquired: {result['file_path']}")
                song_uuid = target_uuid or result.get("uuid")
                features = None
                if song_uuid:
                    fetched = await db.execute(
                        select(Song).options(selectinload(Song.features)).where(Song.uuid == song_uuid)
                    )
                    fetched_song = fetched.scalar_one_or_none()
                    features = _extract_features_from_song(fetched_song) if fetched_song else None
                    artwork_url = fetched_song.artwork_url if fetched_song else None
                
                return {
                    "uuid": target_uuid or result.get('uuid'),
                    "title": result['title'],
                    "artist": result['artist'],
                    "local_path": result['file_path'],
                    "duration_sec": result['duration_sec'],
                    "artwork_url": artwork_url,
                    "features": features,
                }
            else:
                logger.warning(f"Failed to download: {artist} - {title}")
                
        except asyncio.TimeoutError:
            logger.error(f"Download timed out after {timeout}s: {artist} - {title}")
        except Exception as e:
            logger.error(f"Error acquiring song: {e}")
            import traceback
            traceback.print_exc()
        
        return None
        
    finally:
        lock.release()
        # Cleanup lock if no longer needed
        async with _download_locks_guard:
            if normalized in _download_locks and not lock.locked():
                del _download_locks[normalized]


def _is_too_similar(song_a: Dict[str, Any], song_b: Dict[str, Any]) -> bool:
    """Detect if two songs are essentially the same (duplicates or near-identical remixes)."""
    # UUID match
    if song_a.get('uuid') and song_b.get('uuid') and song_a.get('uuid') == song_b.get('uuid'):
        return True
    
    # Artist/Title similarity (normalized)
    norm_a = _normalize_query(song_a.get('artist', ''), song_a.get('title', ''))
    norm_b = _normalize_query(song_b.get('artist', ''), song_b.get('title', ''))
    
    if norm_a == norm_b:
        return True
        
    # Check for (Remix), [Remix], etc. of same song
    base_a = norm_a.split('(')[0].split('[')[0].strip()
    base_b = norm_b.split('(')[0].split('[')[0].strip()
    
    if base_a == base_b and len(base_a) > 5:
        # Same base song, check artist
        artist_a = song_a.get('artist', '').lower().strip()
        artist_b = song_b.get('artist', '').lower().strip()
        if artist_a in artist_b or artist_b in artist_a:
            return True
            
    return False


def _is_too_similar_to_history(
    suggestion: Dict[str, Any],
    history_items: List[HistoryItem],
) -> bool:
    """Check if a suggestion is too similar to recent history tracks."""
    for item in history_items:
        if not item.artist and not item.title:
            continue
        history_song = {
            "artist": item.artist or "",
            "title": item.title or "",
        }
        if _is_too_similar(suggestion, history_song):
            return True
    return False


# =============================================================================
# Track Selector Agent
# =============================================================================

async def select_track(
    db: AsyncSession,
    bundle: PreferenceBundle,
    state: DJState,
    prev_song: Optional[Dict[str, Any]] = None,
    history_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Select next track using deterministic scoring + LLM refinement.
    
    Args:
        db: Database session
        bundle: User's preference bundle
        state: Current DJ state
        prev_song: Previous song for transition context
        history_ids: Optional list of recently played song UUIDs
        
    Returns:
        Selected song dict with uuid, title, artist, local_path, or None
    """
    logger.info(f"Selecting track for user {bundle.user_id}")
    
    # Use bundle history if not provided
    if history_ids is None:
        history_ids = bundle.history.recent_plays
    
    # Step 1: Try Open Selection (AI picks any song, we download or use cached)
    client = get_openrouter_client()
    if client.enabled:
        logger.info("🎯 STEP 1: Asking AI to suggest the perfect song (Open Choice)...")
        suggestion = await client.generate_song_suggestion(bundle, prev_song)
        
        if suggestion:
            artist = suggestion.get('artist')
            title = suggestion.get('title')
            rationale = suggestion.get('rationale', 'AI suggestion')
            logger.info(f"🎵 AI suggested: {artist} - {title}")
            
            # Guard: check if AI suggested something too similar to previous or in history
            suggestion_song = {"artist": artist, "title": title}
            if prev_song and _is_too_similar(prev_song, suggestion_song):
                logger.warning(f"❌ AI suggested song too similar to previous: {artist} - {title}. Rejecting.")
            elif _is_too_similar_to_history(suggestion_song, bundle.history.recent_tracks):
                logger.warning(f"❌ AI suggested song already in recent history: {artist} - {title}. Rejecting.")
            else:
                # Get disliked artists, but exclude favorite artists to prevent over-blocking
                # (disliking one song shouldn't block a favorite artist entirely)
                disliked_artists = [a.lower() for a in bundle.get_disliked_artists() if a]
                favorite_artists = [a.lower() for a in bundle.get_favorite_artists() if a]
                
                # Remove favorite artists from the disliked list
                filtered_disliked = [da for da in disliked_artists if not any(fa in da or da in fa for fa in favorite_artists)]
                
                if artist and any(da in artist.lower() for da in filtered_disliked):
                    logger.warning(f"❌ AI suggested disliked artist: {artist} - {title}. Rejecting.")
                else:
                    # Attempt acquisition (Check Cache -> Download)
                    logger.info(f"📥 Attempting to acquire: {artist} - {title}")
                    acquired = await acquire_song_by_name(
                        db, artist, title, timeout_seconds=45
                    )
                    
                    if acquired:
                        # Final check against history UUID
                        if acquired.get('uuid') in history_ids:
                            logger.warning(f"❌ AI suggested song found in history: {artist} - {title}. Rejecting.")
                        else:
                            # Apply feedback/hard-ban checks even for open choice
                            score = score_candidate(acquired, bundle, prev_song)
                            if score < 0:
                                logger.warning(f"❌ AI suggested song rejected by feedback rules: {artist} - {title}.")
                            else:
                                logger.info(f"✅ OPEN SELECTION SUCCESS: {artist} - {title}")
                                return {
                                    **acquired,
                                    "rationale": rationale,
                                    "selection_method": "ai_open_choice",
                                }
                    else:
                        logger.warning(f"❌ Failed to acquire: {artist} - {title}")
        else:
            logger.warning("❌ AI did not return a suggestion")
    else:
        logger.info("⚠ OpenRouter client disabled, skipping Open Selection")
    
    # Step 2: Fallback to Local Library Scoring if AI selection fails
    logger.warning("⚠ STEP 2: Open Selection failed/disabled. Falling back to local library.")
    scored = await get_scored_candidates(db, bundle, prev_song, history_ids=history_ids, limit=15)
    
    if not scored:
        logger.warning("No candidate songs available in library.")
        return None
    
    # Prepare candidates with scores for LLM refinement
    candidates = [
        {**song, "score": score}
        for song, score in scored
    ]
    
    # Step 2: Call LLM for final selection (with fallback)
    client = get_openrouter_client()
    
    if client.enabled:
        try:
            result = await client.generate_track_selection(
                bundle=bundle,
                candidates=candidates,
                prev_song=prev_song,
            )
            
            if result and result.get('parsed'):
                selected_uuid = result['parsed'].get('selected_uuid')
                rationale = result['parsed'].get('rationale', 'AI selection')
                
                # Find the selected song
                for song, _ in scored:
                    if song.get('uuid') == selected_uuid:
                        logger.info(f"LLM selected: {song.get('artist')} - {song.get('title')}")
                        
                        # Store trace
                        await store_llm_trace(
                            db=db,
                            user_id=bundle.user_id,
                            mood_id=bundle.mood.id,
                            session_id=bundle.session_id,
                            agent_name="track_selector",
                            prompt=f"Candidates: {len(candidates)}",
                            response=f"Selected: {selected_uuid} - {rationale}",
                            model=result.get('model', 'unknown'),
                        )
                        
                        return {
                            **song,
                            "rationale": rationale,
                            "selection_method": "llm",
                        }
                
                logger.warning(f"LLM selected unknown UUID: {selected_uuid}")
        
        except Exception as e:
            logger.error(f"LLM track selection failed: {e}")
    
    # Step 3: Fallback to top deterministic candidate
    if scored:
        song, score = scored[0]
        logger.info(f"Fallback selection: {song.get('artist')} - {song.get('title')} (score={score:.2f})")
        return {
            **song,
            "rationale": f"Top scored candidate (score={score:.2f})",
            "selection_method": "deterministic",
        }
    
    return None


async def select_track_via_catalog(
    db: AsyncSession,
    bundle: PreferenceBundle,
    state: DJState,
    prev_song: Optional[Dict[str, Any]] = None,
    history_ids: Optional[List[str]] = None,
    use_intent_flow: bool = True,
) -> Optional[Dict[str, Any]]:
    """Select track via global catalog with intent-based acquisition.
    
    NEW FLOW (2024-12):
    1. Search global catalog (Deezer) for mood-matching tracks
    2. Apply MMR diversity ranking
    3. Create TrackIntent
    4. Acquire audio file (local cache -> YouTube -> alternatives)
    5. Return Song on success, or fallback to local library
    
    Args:
        db: Database session
        bundle: User's preference bundle
        state: Current DJ state (contains session_id)
        prev_song: Previous song for transition context
        history_ids: Optional list of recently played song UUIDs
        use_intent_flow: If True, use TrackIntent flow; if False, use legacy flow
        
    Returns:
        Song dict with uuid, title, artist, local_path, or None
    """
    logger.info(f"🎯 NEW FLOW: Selecting track via global catalog for user {bundle.user_id}")
    metrics = get_metrics()
    
    session_id = state.get("session_id", "unknown")
    
    if not use_intent_flow:
        # Fallback to legacy flow
        logger.info("Intent flow disabled, using legacy select_track()")
        return await select_track(db, bundle, state, prev_song, history_ids)
    
    try:
        # Use bundle history if not provided
        if history_ids is None:
            history_ids = bundle.history.recent_plays
        
        # Convert recent history to CatalogTrack format for diversity
        recent_catalog_tracks = []
        for hist_item in bundle.history.recent_tracks[:10]:
            # Fix Issue #2: HistoryItem is a dataclass, use attribute access not dict
            if hist_item.artist and hist_item.title:
                # Simplified catalog track from history
                from backend_v2.catalog.providers import CatalogTrack, AudioFeatures
                recent_catalog_tracks.append(CatalogTrack(
                    title=hist_item.title,
                    artist=hist_item.artist,
                    features=AudioFeatures(
                        energy=None,  # HistoryItem doesn't store features
                        valence=None,
                        tempo=None,
                    )
                ))
        
        # Convert prev_song to CatalogTrack if available
        prev_catalog_track = None
        if prev_song:
            prev_features = prev_song.get("features") or {}
            prev_catalog_track = CatalogTrack(
                title=prev_song.get('title', ''),
                artist=prev_song.get('artist', ''),
                features=AudioFeatures(
                    energy=prev_features.get("energy"),
                    valence=prev_features.get("valence"),
                    tempo=prev_features.get("tempo"),
                    danceability=prev_features.get("danceability"),
                )
            )
        
        # Step 1: Select from global catalog with diversity
        logger.info("📚 Searching global catalog with MMR diversity...")
        selected_catalog_track = await select_diverse_track(
            bundle=bundle,
            prev_track=prev_catalog_track,
            recent_tracks=recent_catalog_tracks,
            lambda_param=0.7  # Balanced relevance/diversity
        )
        
        if not selected_catalog_track:
            logger.warning("❌ No tracks found in catalog search")
            metrics.record_local_library_fallback()
            # Fallback to local library
            # Fix Issue #3: Pass all required arguments to select_track
            return await select_track(db, bundle, state, prev_song, history_ids)
        
        logger.info(f"✅ Selected from catalog: {selected_catalog_track.artist} - {selected_catalog_track.title}")
        metrics.record_catalog_selection()
        
        # Step 2: Create TrackIntent
        intent = TrackIntent(
            user_id=bundle.user_id,
            mood_id=bundle.mood.id,
            session_id=session_id or "unknown",
            title=selected_catalog_track.title,
            artist=selected_catalog_track.artist,
            album=selected_catalog_track.album,
            isrc=selected_catalog_track.isrc,
            status=TrackIntentStatus.PENDING.value,
            selection_rationale=f"Selected from catalog (provider={selected_catalog_track.provider})",
            selection_method="catalog_discovery",
        )
        db.add(intent)
        await db.flush()
        
        logger.info(f"📝 Created TrackIntent: {intent.id}")
        
        # Step 3: Acquire audio file
        logger.info(f"📥 Acquiring audio file...")
        acquisition_service = get_acquisition_service()
        
        start_time = utc_now()
        success = await acquisition_service.acquire(db, intent, timeout_per_provider=120)
        duration_sec = (utc_now() - start_time).total_seconds()
        
        if success:
            logger.info(f"✅ Acquisition successful in {duration_sec:.1f}s: {intent.artist} - {intent.title}")
            metrics.record_acquisition_success("catalog_flow", duration_sec)
            
            # Load the acquired song
            from backend_v2.models.existing import Song
            result = await db.execute(
                select(Song).where(Song.uuid == intent.acquired_song_uuid)
            )
            song = result.scalar_one_or_none()
            
            if song:
                # Fix Issue #4 & #5: song.features is scalar (not list), use correct field name, and nest features
                features = song.features
                return {
                    "uuid": song.uuid,
                    "title": song.title,
                    "artist": song.artist,
                    "local_path": song.local_path,
                    "features": {
                        "energy": features.energy if features else None,
                        "valence": features.valence if features else None,
                        "tempo": features.tempo if features else None,
                        "key": features.key if features else None,
                        "mode": features.mode if features else None,
                        "danceability": features.danceability if features else None,
                        "acousticness": features.acousticness if features else None,
                        "instrumentalness": features.instrumentalness if features else None,
                    },
                    "rationale": intent.selection_rationale or "Catalog selection",
                    "selection_method": "catalog_intent",
                }
        else:
            logger.warning(f"❌ Acquisition failed after {duration_sec:.1f}s: {intent.artist} - {intent.title}")
            metrics.record_acquisition_failure("catalog_flow")
            metrics.record_fallback()
            
            # Fallback: Try to select alternative from catalog or local library
            logger.info("🔄 Attempting fallback selection...")
            
            # Exclude the failed track and history
            from backend_v2.catalog.selector import search_catalog_tracks
            excluded = {f"{intent.artist.lower()}|{intent.title.lower()}"}
            for track in recent_catalog_tracks:
                excluded.add(f"{track.artist.lower()}|{track.title.lower()}")
            # Also exclude history UUIDs (convert to titles if we have them)
            # This is a simplified exclusion - in production, you'd want to query DB for titles
            
            # Try one more catalog search
            scored_tracks = await search_catalog_tracks(
                bundle,
                prev_track=prev_catalog_track,
                excluded_titles=excluded,
                limit=50
            )
            
            if scored_tracks and len(scored_tracks) > 0:
                # Take next best option
                fallback_track = scored_tracks[0][0]
                logger.info(f"🔄 Fallback catalog track: {fallback_track.artist} - {fallback_track.title}")
                
                # Create new intent for fallback
                fallback_intent = TrackIntent(
                    user_id=bundle.user_id,
                    mood_id=bundle.mood.id,
                    session_id=session_id or "unknown",
                    title=fallback_track.title,
                    artist=fallback_track.artist,
                    album=fallback_track.album,
                    status=TrackIntentStatus.PENDING.value,
                    selection_rationale="Fallback after acquisition failure",
                    selection_method="catalog_fallback",
                )
                db.add(fallback_intent)
                await db.flush()
                
                success = await acquisition_service.acquire(db, fallback_intent, timeout_per_provider=60)
                
                if success:
                    logger.info(f"✅ Fallback acquisition successful")
                    from backend_v2.models.existing import Song
                    result = await db.execute(
                        select(Song).where(Song.uuid == fallback_intent.acquired_song_uuid)
                    )
                    song = result.scalar_one_or_none()
                    
                    if song:
                        # Include features for consistency with main acquisition path
                        features = song.features
                        return {
                            "uuid": song.uuid,
                            "title": song.title,
                            "artist": song.artist,
                            "local_path": song.local_path,
                            "features": {
                                "energy": features.energy if features else None,
                                "valence": features.valence if features else None,
                                "tempo": features.tempo if features else None,
                                "key": features.key if features else None,
                                "mode": features.mode if features else None,
                                "danceability": features.danceability if features else None,
                                "acousticness": features.acousticness if features else None,
                                "instrumentalness": features.instrumentalness if features else None,
                            },
                            "rationale": "Fallback acquisition",
                            "selection_method": "catalog_fallback",
                        }
            
            # Final fallback: local library
            logger.warning("⚠️ Catalog acquisition failed, falling back to local library")
            metrics.record_local_library_fallback()
            return await select_track(db, bundle, state, prev_song, history_ids)
    
    except Exception as e:
        logger.error(f"Error in catalog selection flow: {e}")
        import traceback
        traceback.print_exc()
        
        # Always fallback to legacy flow on error
        metrics.record_local_library_fallback()
        return await select_track(db, bundle, state, prev_song, history_ids)


# =============================================================================
# Transition Planner Agent
# =============================================================================

async def plan_transition(
    db: AsyncSession,
    bundle: PreferenceBundle,
    song_a: Dict[str, Any],
    song_b: Dict[str, Any],
    recent_transition_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Plan transition between two songs.
    
    Args:
        db: Database session
        bundle: User's preference bundle
        song_a: Current song with features
        song_b: Next song with features
        
    Returns:
        Transition plan dict with type, mix_length_bars, start_position_b_seconds
    """
    logger.info(f"Planning transition: {song_a.get('title') if song_a else 'None'} -> {song_b.get('title') if song_b else 'None'}")
    
    if not song_a or not song_b:
        logger.warning("Missing song_a or song_b for transition planning")
        return {
            "transition_type": "crossfade",
            "mix_length_bars": 16,
            "start_position_b_seconds": 0.0,
            "rationale": "Fallback: Missing song data",
        }
    
    client = get_openrouter_client()

    allowed_transitions = [
        "crossfade",
        "eq_blend",
        "filter_sweep",
        "bass_swap",
        "quick_cut",
        "vinyl_stop",
        "loop_mix",
        "drop_mix",
    ]
    recent_transition_types = [t for t in (recent_transition_types or []) if t]
    
    # Default fallback
    default_plan = {
        "transition_type": "crossfade",
        "mix_length_bars": 16,
        "start_position_b_seconds": 0.0,
        "rationale": "Default crossfade",
    }

    def _pick_fallback_transition() -> Tuple[str, str]:
        """Choose a deterministic transition type based on tempo/energy and history."""
        features_a = song_a.get("features") or {}
        features_b = song_b.get("features") or {}
        
        bpm_a = features_a.get("tempo")
        bpm_b = features_b.get("tempo")
        energy_a = features_a.get("energy")
        energy_b = features_b.get("energy")

        bpm_gap = abs(bpm_a - bpm_b) if bpm_a and bpm_b else None
        energy_gap = abs(energy_a - energy_b) if energy_a is not None and energy_b is not None else None

        preferred = None
        reason = "fallback selection"

        if bpm_gap is not None and bpm_gap >= 20:
            preferred = "quick_cut"
            reason = f"large BPM gap ({bpm_gap:.1f})"
        elif bpm_gap is not None and bpm_gap <= 3:
            preferred = "bass_swap"
            reason = f"tight BPM match ({bpm_gap:.1f})"
        elif energy_gap is not None and energy_gap >= 0.35:
            preferred = "filter_sweep"
            reason = f"energy shift ({energy_gap:.2f})"
        else:
            preferred = "eq_blend"
            reason = "smooth blend"

        if preferred in recent_transition_types:
            for candidate in allowed_transitions:
                if candidate not in recent_transition_types:
                    return candidate, f"avoid repeat ({preferred})"

        return preferred, reason
    
    if not client.enabled:
        fallback_type, reason = _pick_fallback_transition()
        default_plan["transition_type"] = fallback_type
        default_plan["rationale"] = f"{default_plan['rationale']} ({reason})"
        return default_plan
    
    try:
        result = await client.generate_transition_plan(
            bundle=bundle,
            song_a=song_a,
            song_b=song_b,
            recent_transition_types=recent_transition_types,
        )
        
        if result and result.get('parsed'):
            plan = result['parsed']

            raw_type = plan.get("transition_type") or default_plan["transition_type"]
            normalized = raw_type.lower().strip()

            if normalized not in allowed_transitions:
                fallback_type, reason = _pick_fallback_transition()
                plan["transition_type"] = fallback_type
                plan["rationale"] = f"{plan.get('rationale', '')} (forced: {reason})".strip()
            elif normalized in recent_transition_types:
                fallback_type, reason = _pick_fallback_transition()
                plan["transition_type"] = fallback_type
                plan["rationale"] = f"{plan.get('rationale', '')} (variety: {reason})".strip()
            
            # Store trace
            await store_llm_trace(
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id,
                session_id=bundle.session_id,
                agent_name="transition_planner",
                prompt=f"{song_a.get('title')} -> {song_b.get('title')}",
                response=f"{plan.get('transition_type')} ({plan.get('rationale', '')})",
                model=result.get('model', 'unknown'),
            )
            
            logger.info(f"Transition plan: {plan.get('transition_type')}")
            return plan
    
    except Exception as e:
        logger.error(f"Transition planning failed: {e}")
    
    fallback_type, reason = _pick_fallback_transition()
    default_plan["transition_type"] = fallback_type
    default_plan["rationale"] = f"{default_plan['rationale']} ({reason})"
    return default_plan


# =============================================================================
# Speech Writer Agent
# =============================================================================

async def write_intro_speech(
    db: AsyncSession,
    bundle: PreferenceBundle,
    song_info: Dict[str, Any],
    banter_history: Optional[List[str]] = None,
) -> Optional[str]:
    """Generate DJ intro speech for set opening.
    
    Uses persona cooldowns to prevent repeating roast topics too frequently.
    
    Args:
        db: Database session
        bundle: User's preference bundle
        song_info: First song info
        banter_history: Recent speeches to avoid repetition
        
    Returns:
        Speech text, or None
    """
    logger.info(f"Writing intro speech for {song_info.get('title')}")
    
    client = get_openrouter_client()
    
    if not client.enabled:
        return None
    
    # Get persona for cooldown-enforced do_not_repeat list
    persona = get_persona_for_user(bundle)
    do_not_repeat = persona.get_do_not_repeat()
    
    if do_not_repeat:
        logger.debug(f"Persona cooldowns active: {do_not_repeat}")
    
    try:
        # Merge banter history with persona do_not_repeat
        combined_history = list(banter_history or [])
        combined_history.extend(do_not_repeat)
        
        result = await client.generate_dj_intro_speech(
            bundle=bundle,
            song_info=song_info,
            banter_history=combined_history,
        )
        
        if result and result.get('parsed') and result['parsed'].get('text'):
            text = result['parsed']['text']
            
            # Update persona cooldowns based on generated speech
            advance_persona_cooldowns(bundle, text)
            
            # Store trace
            await store_llm_trace(
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id,
                session_id=bundle.session_id,
                agent_name="speech_writer_intro",
                prompt=f"Intro for: {song_info.get('title')}",
                response=text[:200],
                model=result.get('model', 'unknown'),
            )
            
            logger.info(f"Generated intro speech: {len(text)} chars")
            return text
    
    except Exception as e:
        logger.error(f"Intro speech generation failed: {e}")
    
    return None


async def write_transition_speech(
    db: AsyncSession,
    bundle: PreferenceBundle,
    context: Dict[str, Any],
    banter_history: Optional[List[str]] = None,
) -> Optional[str]:
    """Generate DJ transition speech.
    
    Uses persona cooldowns to prevent repeating roast topics too frequently.
    
    Args:
        db: Database session
        bundle: User's preference bundle
        context: Transition context (prev_song, next_song, etc.)
        banter_history: Recent speeches to avoid repetition
        
    Returns:
        Speech text, or None if DJ should stay silent
    """
    logger.info("Writing transition speech")
    
    client = get_openrouter_client()
    
    if not client.enabled:
        return None
    
    # Get persona for cooldown-enforced do_not_repeat list
    persona = get_persona_for_user(bundle)
    do_not_repeat = persona.get_do_not_repeat()
    
    if do_not_repeat:
        logger.debug(f"Persona cooldowns active: {do_not_repeat}")
    
    try:
        # Merge banter history with persona do_not_repeat
        combined_history = list(banter_history or [])
        combined_history.extend(do_not_repeat)
        
        result = await client.generate_dj_speech(
            bundle=bundle,
            context=context,
            banter_history=combined_history,
        )
        
        if result and result.get('parsed') and result['parsed'].get('text'):
            text = result['parsed']['text']
            
            # Update persona cooldowns based on generated speech
            advance_persona_cooldowns(bundle, text)
            
            # Store trace
            await store_llm_trace(
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id,
                session_id=bundle.session_id,
                agent_name="speech_writer",
                prompt=f"Context: {list(context.keys())}",
                response=text[:200],
                model=result.get('model', 'unknown'),
            )
            
            logger.info(f"Generated transition speech: {len(text)} chars")
            return text
    
    except Exception as e:
        logger.error(f"Transition speech generation failed: {e}")
    
    return None


# =============================================================================
# TTS Agent
# =============================================================================

async def synthesize_speech(
    bundle: PreferenceBundle,
    script: str,
    filename_prefix: str = "tts",
) -> Optional[str]:
    """Synthesize speech using ElevenLabs.
    
    Args:
        bundle: User's preference bundle (for per-user voice settings)
        script: Text to synthesize
        filename_prefix: Prefix for output filename
        
    Returns:
        Path to TTS audio file, or None
    """
    if not script or not script.strip():
        return None
    
    logger.info(f"Synthesizing speech: {len(script)} chars")
    
    client = get_elevenlabs_client()
    
    if not client.enabled:
        logger.warning("ElevenLabs client disabled")
        return None
    
    try:
        output_path = await client.synthesize_from_bundle(
            text=script,
            bundle=bundle,
        )
        
        if output_path:
            logger.info(f"TTS synthesized: {output_path}")
        
        return output_path
    
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        return None


# =============================================================================
# Persistence Helpers
# =============================================================================

async def persist_segment(
    db: AsyncSession,
    user_id: str,
    mood_id: Optional[str],
    session_id: str,
    segment_index: int,
    song_uuid: Optional[str],
    file_path: str,
    duration_sec: float,
    tts_used: bool = False,
    banter_text: Optional[str] = None,
):
    """Persist rendered segment to database."""
    from backend_v2.models.existing import Segment
    
    segment = Segment(
        session_id=session_id,
        user_id=user_id,
        mood_id=mood_id,
        segment_index=segment_index,
        song_uuid=song_uuid,
        file_path_transport=file_path,
        duration_sec=duration_sec,
        tts_used=1 if tts_used else 0,
        banter_text=banter_text,
        created_at=utc_isoformat(utc_now()),
    )
    db.add(segment)
    await db.flush()
    
    logger.debug(f"Persisted segment {segment_index}")


async def persist_play_history(
    db: AsyncSession,
    user_id: str,
    mood_id: Optional[str],
    session_id: str,
    song_uuid: str,
    transition_type: Optional[str] = None,
):
    """Record song play in history."""
    from backend_v2.models.existing import PlayHistory
    
    history = PlayHistory(
        session_id=session_id,
        user_id=user_id,
        mood_id=mood_id,
        song_uuid=song_uuid,
        started_at=utc_isoformat(utc_now()),
        transition_type=transition_type,
    )
    db.add(history)
    await db.flush()
    get_bundle_cache().invalidate(user_id)
    
    logger.debug(f"Recorded play history: {song_uuid}")


# =============================================================================
# Policy: Should DJ Speak?
# =============================================================================

def should_dj_speak(
    bundle: PreferenceBundle,
    songs_since_last_speech: int,
    is_intro: bool = False,
) -> bool:
    """Decide if DJ should speak based on personality and timing.
    
    Args:
        bundle: User's preference bundle
        songs_since_last_speech: Songs played since last speech
        is_intro: Whether this is the set intro
        
    Returns:
        True if DJ should speak, False otherwise
    """
    # Always speak on intro
    if is_intro:
        return True
    
    personality = bundle.mood.dj_personality
    
    # Thresholds by personality
    thresholds = {
        "minimal": 5,   # Speak every ~5 songs
        "chill": 3,     # Speak every ~3 songs  
        "chatty": 2,    # Speak every ~2 songs
    }
    
    threshold = thresholds.get(personality, 3)
    
    return songs_since_last_speech >= threshold
