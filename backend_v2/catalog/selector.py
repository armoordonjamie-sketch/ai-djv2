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
    
    # Artist affinity boost
    favorite_artists = [a.lower() for a in bundle.get_favorite_artists() if a]
    if favorite_artists and any(fa in track.artist.lower() for fa in favorite_artists):
        score += 0.15
    
    # Popularity boost (if available, normalized to 0-1)
    if track.popularity:
        score += (track.popularity / 100.0) * 0.1
    
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
    limit: int = 100
) -> List[Tuple[CatalogTrack, float]]:
    """Search catalog for tracks matching mood and score them.
    
    Args:
        bundle: User's preference bundle
        prev_track: Previous track for transition context
        excluded_titles: Set of track titles to exclude (already played)
        limit: Max candidates to return
        
    Returns:
        List of (track, score) tuples sorted by relevance
    """
    excluded_titles = excluded_titles or set()
    
    # Build search query from mood context
    query_parts = []
    
    # Add genre seeds from mood
    if bundle.mood.genre_seeds:
        # Use first 2 genre seeds for query
        query_parts.extend(bundle.mood.genre_seeds[:2])
    
    # Add user's favorite genres if no mood genres
    if not query_parts:
        query_parts.extend(bundle.get_favorite_genres()[:2])
    
    # Fallback to generic query
    if not query_parts:
        query_parts.append(bundle.mood.name.lower())
    
    query = " ".join(query_parts)
    
    logger.info(f"Searching catalog with query: '{query}' (limit={limit})")
    
    # Get providers (currently just Deezer)
    providers: List[CatalogProvider] = [get_deezer_provider()]
    
    # Search all providers
    all_tracks = []
    for provider in providers:
        if not provider.enabled:
            continue
        
        try:
            tracks = await provider.search_tracks(query, limit=limit)
            logger.info(f"Provider {provider.name}: found {len(tracks)} tracks")
            all_tracks.extend(tracks)
        except Exception as e:
            logger.error(f"Provider {provider.name} search failed: {e}")
    
    # Filter out excluded tracks
    filtered_tracks = [
        t for t in all_tracks
        if f"{t.artist.lower()}|{t.title.lower()}" not in excluded_titles
    ]
    
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
    
    # Search catalog
    scored_tracks = await search_catalog_tracks(
        bundle,
        prev_track=prev_track,
        excluded_titles=excluded,
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

