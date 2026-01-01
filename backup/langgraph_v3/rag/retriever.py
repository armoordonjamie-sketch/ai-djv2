"""
RAG Retriever - Retrieve tracks using vector similarity.

This module handles:
1. Building retrieval queries from state
2. Vector similarity search
3. Result filtering and ranking
"""
import logging
from typing import Any, Dict, List, Optional

from backend_v2.langgraph_v3.state import DJStateV3

logger = logging.getLogger("ai-dj.rag.retriever")


async def retrieve_tracks(
    state: DJStateV3,
    k: int = 8,
) -> List[Dict[str, Any]]:
    """
    Retrieve candidate tracks using vector similarity.
    
    Args:
        state: Current DJ state
        k: Number of tracks to retrieve
        
    Returns:
        List of track dicts with metadata
    """
    from backend_v2.langgraph_v3.rag.index import get_vectorstore
    
    vectorstore = get_vectorstore()
    if not vectorstore:
        logger.warning("Vector store not available")
        return []
    
    # Build query from state
    query = build_retrieval_query(state)
    
    if not query:
        logger.warning("Could not build retrieval query")
        return []
    
    logger.debug(f"Retrieving with query: {query[:100]}...")
    
    try:
        # Perform similarity search
        docs = await vectorstore.asimilarity_search_with_score(query, k=k * 2)
        
        # Filter and process results
        results = []
        songs_played = set(state.get("songs_played", []))
        disliked_uuids = set(state.get("disliked_uuids", []))
        blocked_artists = set(a.lower() for a in state.get("blocked_artists", []))
        
        for doc, score in docs:
            metadata = doc.metadata
            uuid = metadata.get("uuid")
            artist = metadata.get("artist", "").lower()
            
            # Skip played songs
            if uuid in songs_played:
                continue
            
            # Skip disliked songs
            if uuid in disliked_uuids:
                continue
            
            # Skip blocked artists
            if artist in blocked_artists:
                continue
            
            results.append({
                "uuid": uuid,
                "title": metadata.get("title", ""),
                "artist": metadata.get("artist", ""),
                "duration_sec": metadata.get("duration_sec"),
                "local_path": metadata.get("local_path"),
                "artwork_url": metadata.get("artwork_url"),
                "bpm": metadata.get("bpm"),
                "energy": metadata.get("energy"),
                "valence": metadata.get("valence"),
                "danceability": metadata.get("danceability"),
                "similarity_score": float(score),
            })
            
            if len(results) >= k:
                break
        
        logger.info(f"Retrieved {len(results)} candidate tracks")
        return results
        
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return []


def build_retrieval_query(state: DJStateV3) -> str:
    """
    Build a retrieval query from state.
    
    Combines mood targets, preferences, and context into a query string.
    """
    parts = []
    
    # Mood targets
    mood_targets = state.get("mood_targets") or {}
    
    if mood_targets.get("mood_name"):
        parts.append(f"Mood: {mood_targets['mood_name']}")
    
    genres = mood_targets.get("genres", [])
    if genres:
        parts.append(f"Genres: {', '.join(genres[:5])}")
    
    example_artists = mood_targets.get("example_artists", [])
    if example_artists:
        parts.append(f"Similar to: {', '.join(example_artists[:5])}")
    
    vibe_keywords = mood_targets.get("vibe_keywords", [])
    if vibe_keywords:
        parts.append(f"Vibe: {', '.join(vibe_keywords[:5])}")
    
    # Energy/valence targets
    energy = mood_targets.get("energy_target", 0.5)
    valence = mood_targets.get("valence_target", 0.5)
    
    if energy > 0.7:
        parts.append("High energy, upbeat")
    elif energy < 0.3:
        parts.append("Low energy, chill")
    
    if valence > 0.7:
        parts.append("Happy, positive")
    elif valence < 0.3:
        parts.append("Melancholic, introspective")
    
    # Spotify context
    spotify_artists = state.get("spotify_top_artists", [])[:3]
    if spotify_artists:
        artist_names = [a.get("name") for a in spotify_artists if a.get("name")]
        if artist_names:
            parts.append(f"User likes: {', '.join(artist_names)}")
    
    spotify_genres = state.get("spotify_genres", [])[:3]
    if spotify_genres:
        parts.append(f"Preferred genres: {', '.join(spotify_genres)}")
    
    # Last song context for flow
    last_song = state.get("last_song") or {}
    if last_song.get("artist"):
        parts.append(f"Following: {last_song['artist']} - {last_song.get('title', '')}")
    
    return "\n".join(parts)


async def retrieve_similar_to_track(
    track: Dict[str, Any],
    k: int = 5,
    exclude_uuids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve tracks similar to a specific track.
    
    Args:
        track: Reference track dict
        k: Number of tracks to retrieve
        exclude_uuids: UUIDs to exclude from results
        
    Returns:
        List of similar track dicts
    """
    from backend_v2.langgraph_v3.rag.index import get_vectorstore
    
    vectorstore = get_vectorstore()
    if not vectorstore:
        return []
    
    # Build query from track
    query_parts = [
        f"Artist: {track.get('artist', '')}",
        f"Title: {track.get('title', '')}",
    ]
    
    genres = track.get("genres", [])
    if genres:
        query_parts.append(f"Genres: {', '.join(genres)}")
    
    if track.get("bpm"):
        query_parts.append(f"BPM: {track['bpm']}")
    if track.get("energy"):
        query_parts.append(f"Energy: {track['energy']}")
    
    query = "\n".join(query_parts)
    
    exclude_set = set(exclude_uuids or [])
    exclude_set.add(track.get("uuid", ""))  # Exclude the reference track
    
    try:
        docs = await vectorstore.asimilarity_search_with_score(query, k=k * 2)
        
        results = []
        for doc, score in docs:
            metadata = doc.metadata
            uuid = metadata.get("uuid")
            
            if uuid in exclude_set:
                continue
            
            results.append({
                "uuid": uuid,
                "title": metadata.get("title", ""),
                "artist": metadata.get("artist", ""),
                "similarity_score": float(score),
            })
            
            if len(results) >= k:
                break
        
        return results
        
    except Exception as e:
        logger.error(f"Similar track retrieval failed: {e}")
        return []
