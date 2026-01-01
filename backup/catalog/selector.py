"""Global catalog selector with MMR (Maximal Marginal Relevance) diversity ranking.

Selects tracks from catalog providers ensuring both relevance to mood and diversity
to prevent repetitive selections.
"""
import logging
import math
from typing import List, Optional, Tuple, Set, TYPE_CHECKING

from backend_v2.catalog.providers import (
    CatalogProvider,
    CatalogTrack,
    get_deezer_provider,
)

if TYPE_CHECKING:
    from backend_v2.services.preference_bundle import PreferenceBundle

logger = logging.getLogger("ai-dj.catalog.selector")


def _normalize_song_title(title: str) -> str:
    """Normalize song title by removing remix/cover indicators.
    
    Examples:
        "Sk8er Boi (Remix)" -> "sk8er boi"
        "Sk8er Boi [Cover]" -> "sk8er boi"
        "Sk8er Boi - Acoustic" -> "sk8er boi"
    """
    if not title:
        return ""
    
    # Remove common remix/cover indicators
    normalized = title.lower().strip()
    
    # Remove parenthetical content: (Remix), [Cover], etc.
    import re
    normalized = re.sub(r'\([^)]*\)', '', normalized)  # Remove (Remix), (Cover), etc.
    normalized = re.sub(r'\[[^\]]*\]', '', normalized)  # Remove [Remix], [Cover], etc.
    
    # Remove common suffixes
    suffixes = [' - remix', ' - cover', ' - acoustic', ' - live', ' - extended']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    
    return normalized.strip()


# Keywords that indicate a track is a mix/compilation (not a single song)
# These tracks are typically 30+ minutes and don't work well for DJ sets
MIX_COMPILATION_KEYWORDS = {
    "mix", "megamix", "compilation", "nonstop", "non-stop", "medley", 
    "mashup", "mash up", "continuous", "dj set", "live set", "party mix",
    "dance party", "club mix", "workout mix", "best of", "greatest hits",
    "2024 hits", "2025 hits", "top 40", "top 100", "various artists",
    "new year", "new years", "nye ", "christmas party", "summer hits",
    "remix album", "the album", "mixed by", "continuous mix",
}


def is_mix_or_compilation(track: CatalogTrack) -> bool:
    """Check if a track appears to be a DJ mix or compilation rather than a single song.
    
    These tracks cause issues:
    - They're typically 30+ minutes long
    - They download slowly
    - They don't work well in DJ sets
    
    Args:
        track: Track to check
        
    Returns:
        True if track appears to be a mix/compilation
    """
    # Check title
    title_lower = track.title.lower()
    for keyword in MIX_COMPILATION_KEYWORDS:
        if keyword in title_lower:
            return True
    
    # Check artist name for DJ mix indicators
    artist_lower = track.artist.lower()
    if any(kw in artist_lower for kw in ["various", "dj mix", "party dj", "club dj"]):
        return True
    
    # Check duration if available (mixes are typically >10 minutes / 600,000 ms)
    if track.duration_ms and track.duration_ms > 600_000:
        return True
    
    return False


def cosine_similarity(vec1: Tuple[float, ...], vec2: Tuple[float, ...]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def track_to_feature_vector(track: CatalogTrack) -> Optional[Tuple[float, ...]]:
    """Convert track to feature vector for similarity calculations."""
    if not track.features:
        return None
    
    # Use available features, defaulting to 0.5 if missing
    energy = track.features.energy if track.features.energy is not None else 0.5
    valence = track.features.valence if track.features.valence is not None else 0.5
    danceability = track.features.danceability if track.features.danceability is not None else 0.5
    
    # Normalize tempo to 0-1 range (assuming 60-180 BPM range)
    tempo = track.features.tempo if track.features.tempo else 120
    tempo_normalized = (tempo - 60) / 120
    tempo_normalized = max(0.0, min(1.0, tempo_normalized))
    
    return (energy, valence, danceability, tempo_normalized)


def score_track_relevance(
    track: CatalogTrack,
    bundle: "PreferenceBundle",
    prev_track: Optional[CatalogTrack] = None
) -> float:
    """Score how well a track matches the mood target and user preferences.
    
    Args:
        track: Catalog track to score
        bundle: User's preference bundle
        prev_track: Previous track for transition compatibility
        
    Returns:
        Score from 0.0 to 1.0 (higher = better match)
    """
    score = 0.5  # Base score
    
    # Mood matching (if features available)
    if track.features:
        # Energy match (weight: 0.3)
        if track.features.energy is not None:
            energy_dist = abs(track.features.energy - bundle.mood.energy_target)
            score += (1.0 - energy_dist) * 0.3
        
        # Valence match (weight: 0.3)
        if track.features.valence is not None:
            valence_dist = abs(track.features.valence - bundle.mood.valence_target)
            score += (1.0 - valence_dist) * 0.3
        
        # Danceability match (weight: 0.2, if target available)
        if track.features.danceability is not None and bundle.mood.danceability_target is not None:
            dance_dist = abs(track.features.danceability - bundle.mood.danceability_target)
            score += (1.0 - dance_dist) * 0.2
        
        # Tempo compatibility with previous track (weight: 0.1)
        if prev_track and prev_track.features and track.features.tempo and prev_track.features.tempo:
            tempo_ratio = track.features.tempo / prev_track.features.tempo
            if 0.95 <= tempo_ratio <= 1.05:
                score += 0.1  # Very close tempo
            elif 0.85 <= tempo_ratio <= 1.15:
                score += 0.05  # Reasonable tempo
        
        # NEW: Energy preference boost
        energy_pref = bundle.get_energy_preference()
        if energy_pref and track.features.energy is not None:
            if energy_pref == "high_energy" and track.features.energy >= 0.7:
                score += 0.1  # Boost high energy tracks for users who prefer them
            elif energy_pref == "low_energy" and track.features.energy <= 0.4:
                score += 0.1  # Boost chill tracks for users who prefer them
        
        # NEW: Tempo preference boost
        tempo_pref = bundle.get_tempo_preference()
        if tempo_pref and track.features.tempo:
            if tempo_pref == "fast" and track.features.tempo >= 120:
                score += 0.08  # Boost fast tracks
            elif tempo_pref == "slow" and track.features.tempo <= 100:
                score += 0.08  # Boost slower tracks
    
    # Artist affinity boost (REDUCED from 0.15 to encourage variety)
    favorite_artists = [a.lower() for a in bundle.get_favorite_artists() if a]
    is_favorite = favorite_artists and any(fa in track.artist.lower() for fa in favorite_artists)
    if is_favorite:
        score += 0.05  # Reduced from 0.15 to prevent favorite artist dominance
    
    # NEW: Favorite song boost - if track title matches a favorite song, big boost!
    favorite_songs = [s.lower() for s in bundle.get_favorite_songs() if s]
    if favorite_songs:
        track_title_lower = track.title.lower()
        for fav_song in favorite_songs:
            # Check if the favorite song name is contained in the track title
            if fav_song in track_title_lower or track_title_lower in fav_song:
                score += 0.2  # Big boost for matching favorite songs
                break
    
    # NOVELTY BONUS: Reward artists NOT in recent history (encourages discovery!)
    history_artists = [a.lower() for a in bundle.history.recent_artists if a]
    is_new_artist = track.artist.lower() not in history_artists
    if is_new_artist:
        score += 0.10  # Bonus for introducing new artists
    
    # Popularity boost (if available, normalized to 0-1)
    if track.popularity:
        score += (track.popularity / 100.0) * 0.1
    
    # NEW: Era preference scoring
    era_pref = bundle.get_era_preference()
    if era_pref and era_pref != "mixed" and era_pref != "no_preference":
        # Use popularity as a proxy for era (newer hits tend to have higher popularity)
        # This is a heuristic - ideally we'd have release_year from Deezer
        if track.popularity:
            if era_pref == "new_releases" and track.popularity >= 70:
                score += 0.08  # Boost popular (likely newer) tracks
            elif era_pref == "classics" and track.popularity < 50:
                score += 0.08  # Boost less popular (likely older/classic) tracks
    
    return min(1.0, max(0.0, score))


def mmr_select(
    scored_tracks: List[Tuple[CatalogTrack, float]],
    selected_tracks: List[CatalogTrack],
    lambda_param: float = 0.7,
    k: int = 1
) -> List[CatalogTrack]:
    """Maximal Marginal Relevance selection for diversity.
    
    MMR balances relevance and diversity:
    - High lambda (0.8-1.0): Favor relevance (mood match)
    - Low lambda (0.4-0.6): Favor diversity (variety)
    - Medium lambda (0.6-0.8): Balanced
    
    Args:
        scored_tracks: List of (track, relevance_score) tuples
        selected_tracks: Already selected tracks (for diversity calculation)
        lambda_param: Balance between relevance and diversity (0-1)
        k: Number of tracks to select
        
    Returns:
        List of k selected tracks
    """
    if not scored_tracks:
        return []
    
    if k <= 0:
        return []
    
    # If no previous selections, just take top k by relevance
    if not selected_tracks:
        sorted_tracks = sorted(scored_tracks, key=lambda x: x[1], reverse=True)
        return [track for track, _ in sorted_tracks[:k]]
    
    # Extract feature vectors for diversity calculation
    selected_vectors = []
    for track in selected_tracks:
        vec = track_to_feature_vector(track)
        if vec:
            selected_vectors.append(vec)
    
    # If no feature vectors available, fall back to relevance-only
    if not selected_vectors:
        sorted_tracks = sorted(scored_tracks, key=lambda x: x[1], reverse=True)
        return [track for track, _ in sorted_tracks[:k]]
    
    # MMR selection
    result = []
    remaining = list(scored_tracks)
    
    for _ in range(min(k, len(remaining))):
        if not remaining:
            break
        
        best_track = None
        best_mmr = -float('inf')
        best_idx = -1
        
        for idx, (track, relevance) in enumerate(remaining):
            track_vec = track_to_feature_vector(track)
            if not track_vec:
                # No features, use relevance only
                mmr_score = relevance
            else:
                # Calculate max similarity to already selected tracks
                max_sim = max(
                    cosine_similarity(track_vec, sel_vec)
                    for sel_vec in selected_vectors
                )
                
                # MMR formula: λ * relevance - (1-λ) * max_similarity
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
            
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_track = track
                best_idx = idx
        
        if best_track:
            result.append(best_track)
            remaining.pop(best_idx)
            
            # Add to selected vectors for next iteration
            vec = track_to_feature_vector(best_track)
            if vec:
                selected_vectors.append(vec)
    
    return result


async def search_catalog_tracks(
    bundle: "PreferenceBundle",
    prev_track: Optional[CatalogTrack] = None,
    excluded_titles: Optional[Set[str]] = None,
    excluded_normalized_titles: Optional[Set[str]] = None,
    limit: int = 100
) -> List[Tuple[CatalogTrack, float]]:
    """Search catalog for tracks matching mood and score them.
    
    Args:
        bundle: User's preference bundle
        prev_track: Previous track for transition context
        excluded_titles: Set of track titles to exclude (already played)
        excluded_normalized_titles: Set of normalized titles to exclude (prevents covers/remixes)
        limit: Max candidates to return
        
    Returns:
        List of (track, score) tuples sorted by relevance
    """
    excluded_titles = excluded_titles or set()
    excluded_normalized_titles = excluded_normalized_titles or set()
    
    # Build search queries - PRIORITIZE MOOD CONTEXT, then add familiar artists
    queries = []
    artist_queries = []  # Track artist-specific queries for filtering
    song_queries = []  # Track song-specific queries for finding exact matches
    
    # Get sources
    favorite_artists = bundle.get_favorite_artists()[:10]
    favorite_songs = bundle.get_favorite_songs()[:5]  # NEW: Get favorite songs
    mood_example_artists = bundle.mood.example_artists or []
    mood_genres = bundle.mood.genres or []
    mood_genre_seeds = bundle.mood.genre_seeds or []
    user_genres = bundle.get_favorite_genres() or []
    
    # NEW: Add Spotify top artists if available (prioritize medium term = last 6 months)
    if bundle.profile.spotify_connected and bundle.profile.top_artists_medium_term:
        spotify_artists = [artist.get("name") for artist in bundle.profile.top_artists_medium_term[:5] if artist.get("name")]
        # Add to favorite_artists if not already present
        for artist in spotify_artists:
            if artist and artist not in favorite_artists:
                favorite_artists.append(artist)
        logger.info(f"🎵 Enhanced search with {len(spotify_artists)} Spotify top artists")
    
    # STRATEGY: Mood context FIRST, then familiar artists, then favorite songs
    # This ensures mood selection actually affects the music!
    
    # Step 1: MOOD EXAMPLE ARTISTS (most important for mood relevance!)
    # Use more artists (up to 5) to better utilize training data
    # Training adds artists at the beginning, so prioritize those
    for artist in mood_example_artists[:5]:
        if artist and artist.lower() not in [q.lower() for q in queries]:
            queries.append(artist)
            artist_queries.append(artist.lower())
    
    # Step 2: If mood name looks like an artist name (not generic), search for it too
    mood_name = bundle.mood.name.strip()
    # Check if it's an artist-like name (contains letters, not just mood words)
    generic_mood_words = {'flow', 'energy', 'chill', 'focus', 'melancholy', 'euphoria', 'calm', 'party', 'workout'}
    if mood_name.lower() not in generic_mood_words and len(mood_name) > 2:
        # Might be an artist-named mood (e.g., "avril lavigne")
        if mood_name.lower() not in [q.lower() for q in queries]:
            queries.append(mood_name)
            artist_queries.append(mood_name.lower())
    
    # Step 3: Add MORE mood genres (key for diversity!)
    all_genres = list(set(mood_genre_seeds + mood_genres))
    for genre in all_genres[:4]:  # Increased from 2 to 4 for more genre diversity
        if genre and genre.lower() not in [q.lower() for q in queries]:
            queries.append(genre)
    
    # Step 4: Add favorite artists (for familiar balance)
    for artist in favorite_artists[:2]:
        if artist and artist.lower() not in [q.lower() for q in queries]:
            queries.append(artist)
            artist_queries.append(artist.lower())
    
    # NEW Step 5: Add favorite songs as search queries (BETTER UTILIZATION!)
    # These help find the exact songs the user loves and similar tracks
    for song in favorite_songs[:3]:
        if song and song.lower() not in [q.lower() for q in queries]:
            queries.append(song)
            song_queries.append(song.lower())
    
    # Fallback if no queries
    if not queries:
        if mood_genres:
            queries.extend(mood_genres[:2])
        elif favorite_artists:
            queries.extend(favorite_artists[:2])
            artist_queries.extend([a.lower() for a in favorite_artists[:2]])
        else:
            queries.append(mood_name.lower() if mood_name else "pop")
    
    logger.info(f"Searching catalog with {len(queries)} queries: {queries[:5]}...")
    
    # Get providers (currently just Deezer)
    provider = get_deezer_provider()
    
    if not provider.enabled:
        logger.warning("Deezer provider not enabled")
        return []
    
    # Search with multiple queries for better diversity
    all_tracks = []
    seen_ids = set()  # Deduplicate tracks across queries
    
    # Distribute limit across queries
    per_query_limit = max(20, limit // len(queries)) if queries else limit
    
    for query in queries:
        try:
            # If this is an artist query (from our artist_queries list), use artist-specific search
            if query.lower() in [a.lower() for a in artist_queries]:
                # Use dedicated artist top tracks search (more reliable)
                tracks = await provider.get_artist_tracks(query, limit=per_query_limit)
            else:
                # Generic search for genres/other queries
                tracks = await provider.search_tracks(query, limit=per_query_limit)
            
            # Deduplicate by provider ID
            new_tracks = [t for t in tracks if t.provider_id not in seen_ids]
            seen_ids.update(t.provider_id for t in new_tracks)
            all_tracks.extend(new_tracks)
            
            if new_tracks:
                logger.debug(f"Query '{query}': {len(new_tracks)} new tracks")
        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}")
    
    logger.info(f"Provider {provider.name}: found {len(all_tracks)} total tracks")
    
    # Filter out excluded tracks, mixes/compilations, and non-matching artist results
    filtered_tracks = []
    mix_count = 0
    wrong_artist_count = 0
    
    for t in all_tracks:
        # Skip already played (exact match)
        if f"{t.artist.lower()}|{t.title.lower()}" in excluded_titles:
            continue
        
        # NEW: Skip if normalized title matches recently played (prevents covers/remixes)
        normalized_title = _normalize_song_title(t.title)
        if normalized_title and normalized_title in excluded_normalized_titles:
            logger.debug(f"🚫 Excluding cover/remix: {t.artist} - {t.title} (normalized: {normalized_title})")
            continue
        
        # Skip mixes and compilations
        if is_mix_or_compilation(t):
            mix_count += 1
            continue
        
        # When searching by artist name, filter out tracks that just mention the artist
        # but aren't actually BY that artist (e.g., "I Love Taylor Swift" by Random DJ)
        if artist_queries:
            track_artist_lower = t.artist.lower()
            # Check if this track is actually by one of our target artists
            is_target_artist = any(
                target_artist in track_artist_lower or track_artist_lower in target_artist
                for target_artist in artist_queries
            )
            if not is_target_artist:
                # Check if track title suspiciously contains artist name (cover/tribute)
                title_lower = t.title.lower()
                has_artist_in_title = any(a in title_lower for a in artist_queries)
                if has_artist_in_title:
                    wrong_artist_count += 1
                    continue  # Skip "I Love X" or "X Cover" tracks
        
        filtered_tracks.append(t)
    
    if mix_count > 0:
        logger.debug(f"Filtered out {mix_count} mixes/compilations")
    if wrong_artist_count > 0:
        logger.debug(f"Filtered out {wrong_artist_count} non-artist tracks (covers/tributes)")
    
    logger.info(f"After filtering: {len(filtered_tracks)} candidates")
    
    # Score each track
    scored = []
    for track in filtered_tracks:
        score = score_track_relevance(track, bundle, prev_track)
        scored.append((track, score))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    return scored[:limit]


async def select_diverse_track(
    bundle: "PreferenceBundle",
    prev_track: Optional[CatalogTrack] = None,
    recent_tracks: Optional[List[CatalogTrack]] = None,
    lambda_param: float = 0.7
) -> Optional[CatalogTrack]:
    """Select a single diverse track from catalog.
    
    This is the main entry point for track selection with diversity.
    
    Args:
        bundle: User's preference bundle
        prev_track: Previous track for transition context
        recent_tracks: Recently played tracks for diversity
        lambda_param: MMR lambda (0.7 = balanced, higher = more relevance focus)
        
    Returns:
        Selected track or None
    """
    recent_tracks = recent_tracks or []
    
    # Build exclusion set from recent tracks
    excluded = {
        f"{t.artist.lower()}|{t.title.lower()}"
        for t in recent_tracks
    }
    
    # Also build normalized title exclusions to prevent covers/remixes
    excluded_normalized = set()
    for t in recent_tracks:
        normalized_title = _normalize_song_title(t.title)
        if normalized_title:
            excluded_normalized.add(normalized_title)
    
    # Search catalog
    scored_tracks = await search_catalog_tracks(
        bundle,
        prev_track=prev_track,
        excluded_titles=excluded,
        excluded_normalized_titles=excluded_normalized,
        limit=100
    )
    
    if not scored_tracks:
        logger.warning("No tracks found in catalog search")
        return None
    
    # Apply MMR selection
    selected = mmr_select(
        scored_tracks,
        selected_tracks=recent_tracks,
        lambda_param=lambda_param,
        k=1
    )
    
    if selected:
        track = selected[0]
        logger.info(f"Selected diverse track: {track.artist} - {track.title}")
        return track
    
    return None

