"""
Long-term memory store for AI DJ v3.

Uses LangGraph's Store interface to persist user preferences, banter constraints,
session summaries, and transition recipes across sessions.

Namespace schema:
- ("user", user_id, "taste")       - Learned preferences from feedback
- ("user", user_id, "banter")      - Roast constraints and topics
- ("user", user_id, "session_summaries") - Session history
- ("user", user_id, "transition_recipes") - Successful transition patterns
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from langgraph.store.memory import InMemoryStore

logger = logging.getLogger("ai-dj.langgraph-memory")

# Global store instance
_store: Optional[InMemoryStore] = None


def get_store() -> InMemoryStore:
    """
    Get or create the global memory store.
    
    Uses InMemoryStore for dev/test. For production, this can be
    swapped to a Postgres-backed store via environment variable.
    """
    global _store
    
    if _store is None:
        store_type = os.environ.get("LANGGRAPH_STORE", "memory")
        
        if store_type == "memory":
            _store = InMemoryStore()
            logger.info("Initialized InMemoryStore for long-term memory")
        else:
            # For now, default to memory store
            # TODO: Add Postgres store when langgraph-checkpoint-postgres is installed
            _store = InMemoryStore()
            logger.warning(f"Store type '{store_type}' not implemented, using InMemoryStore")
    
    return _store


# =============================================================================
# Namespace Constants
# =============================================================================

NAMESPACE_TASTE = "taste"
NAMESPACE_BANTER = "banter"
NAMESPACE_SESSION_SUMMARIES = "session_summaries"
NAMESPACE_TRANSITION_RECIPES = "transition_recipes"


# =============================================================================
# Memory Operations
# =============================================================================

async def load_user_memory(user_id: str) -> Dict[str, Any]:
    """
    Load all memory for a user.
    
    Returns a dict with:
    - taste: Dict of preference weights
    - banter: Dict of roast constraints
    - session_summaries: List of recent session summaries
    - transition_recipes: List of successful transition patterns
    """
    store = get_store()
    
    result = {
        "taste": {},
        "banter": {},
        "session_summaries": [],
        "transition_recipes": [],
    }
    
    try:
        # Load taste preferences
        taste_items = await store.aget(("user", user_id, NAMESPACE_TASTE), "preferences")
        if taste_items:
            result["taste"] = taste_items.value if hasattr(taste_items, "value") else taste_items
        
        # Load banter constraints
        banter_items = await store.aget(("user", user_id, NAMESPACE_BANTER), "constraints")
        if banter_items:
            result["banter"] = banter_items.value if hasattr(banter_items, "value") else banter_items
        
        # Load session summaries (get last 10)
        summaries = await store.aget(("user", user_id, NAMESPACE_SESSION_SUMMARIES), "recent")
        if summaries:
            result["session_summaries"] = (summaries.value if hasattr(summaries, "value") else summaries) or []
        
        # Load transition recipes (get last 20)
        recipes = await store.aget(("user", user_id, NAMESPACE_TRANSITION_RECIPES), "successful")
        if recipes:
            result["transition_recipes"] = (recipes.value if hasattr(recipes, "value") else recipes) or []
        
        logger.debug(f"Loaded memory for user {user_id}: taste={len(result['taste'])} keys, "
                    f"sessions={len(result['session_summaries'])}, recipes={len(result['transition_recipes'])}")
        
    except Exception as e:
        logger.warning(f"Error loading user memory: {e}")
    
    return result


async def write_memory(
    user_id: str,
    namespace: str,
    key: str,
    value: Any,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Write a value to user memory.
    
    Args:
        user_id: User ID
        namespace: One of taste, banter, session_summaries, transition_recipes
        key: Key within the namespace
        value: Value to store
        metadata: Optional metadata
        
    Returns:
        True if successful
    """
    store = get_store()
    
    try:
        await store.aput(
            ("user", user_id, namespace),
            key,
            value,
            index=metadata if metadata else None,
        )
        logger.debug(f"Wrote memory: user={user_id}, namespace={namespace}, key={key}")
        return True
    except Exception as e:
        logger.error(f"Error writing memory: {e}")
        return False


async def update_taste_preferences(
    user_id: str,
    updates: Dict[str, float],
    learning_rate: float = 0.1,
) -> Dict[str, float]:
    """
    Update taste preferences using simple online learning.
    
    Args:
        user_id: User ID
        updates: Dict of preference key -> delta (-1 to 1)
        learning_rate: How fast to update (0.1 = 10% adjustment per update)
        
    Returns:
        Updated preferences dict
    """
    store = get_store()
    
    # Load current preferences
    current_item = await store.aget(("user", user_id, NAMESPACE_TASTE), "preferences")
    current = {}
    if current_item:
        current = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(current, dict):
            current = {}
    
    # Apply updates with learning rate
    for key, delta in updates.items():
        old_value = current.get(key, 0.5)  # Default to neutral
        new_value = old_value + (delta * learning_rate)
        # Clamp to [0, 1]
        current[key] = max(0.0, min(1.0, new_value))
    
    # Save updated preferences
    await store.aput(("user", user_id, NAMESPACE_TASTE), "preferences", current)
    
    logger.info(f"Updated taste preferences for user {user_id}: {len(updates)} keys adjusted")
    return current


async def update_banter_constraints(
    user_id: str,
    topics_used: List[str],
    off_limits: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Update banter constraints after speech generation.
    
    Args:
        user_id: User ID
        topics_used: Roast topics that were used this segment
        off_limits: Topics to mark as off-limits (user indicated they don't like)
        
    Returns:
        Updated banter constraints
    """
    store = get_store()
    
    # Load current constraints
    current_item = await store.aget(("user", user_id, NAMESPACE_BANTER), "constraints")
    current = {"roast_topics_used": [], "off_limits": [], "last_updated": None}
    if current_item:
        current = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(current, dict):
            current = {"roast_topics_used": [], "off_limits": [], "last_updated": None}
    
    # Add used topics (keep last 50)
    used = current.get("roast_topics_used", [])
    if isinstance(used, list):
        used.extend(topics_used)
        current["roast_topics_used"] = used[-50:]
    
    # Add off-limits topics
    if off_limits:
        limits = current.get("off_limits", [])
        if isinstance(limits, list):
            for topic in off_limits:
                if topic not in limits:
                    limits.append(topic)
            current["off_limits"] = limits
    
    current["last_updated"] = datetime.utcnow().isoformat()
    
    # Save
    await store.aput(("user", user_id, NAMESPACE_BANTER), "constraints", current)
    
    return current


async def add_session_summary(
    user_id: str,
    session_id: str,
    summary: str,
    tracks_played: int,
    duration_minutes: float,
    mood_name: Optional[str] = None,
) -> None:
    """
    Add a session summary to user memory.
    
    Args:
        user_id: User ID
        session_id: Session ID
        summary: Natural language summary of the session
        tracks_played: Number of tracks played
        duration_minutes: Session duration in minutes
        mood_name: Name of the mood used
    """
    store = get_store()
    
    # Load existing summaries
    current_item = await store.aget(("user", user_id, NAMESPACE_SESSION_SUMMARIES), "recent")
    summaries = []
    if current_item:
        summaries = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(summaries, list):
            summaries = []
    
    # Add new summary
    new_summary = {
        "session_id": session_id,
        "summary": summary,
        "tracks_played": tracks_played,
        "duration_minutes": duration_minutes,
        "mood_name": mood_name,
        "timestamp": datetime.utcnow().isoformat(),
    }
    summaries.append(new_summary)
    
    # Keep last 20 summaries
    summaries = summaries[-20:]
    
    # Save
    await store.aput(("user", user_id, NAMESPACE_SESSION_SUMMARIES), "recent", summaries)
    
    logger.debug(f"Added session summary for user {user_id}: {session_id}")


async def add_transition_recipe(
    user_id: str,
    from_genre: str,
    to_genre: str,
    transition_type: str,
    success: bool,
    energy_delta: float,
    bpm_delta: float,
) -> None:
    """
    Record a transition recipe outcome.
    
    Args:
        user_id: User ID
        from_genre: Genre of Song A
        to_genre: Genre of Song B
        transition_type: Type of transition used
        success: Whether it worked well (user didn't skip immediately)
        energy_delta: Energy difference between tracks
        bpm_delta: BPM difference between tracks
    """
    store = get_store()
    
    # Load existing recipes
    current_item = await store.aget(("user", user_id, NAMESPACE_TRANSITION_RECIPES), "successful")
    recipes = []
    if current_item:
        recipes = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(recipes, list):
            recipes = []
    
    # Add new recipe
    recipe = {
        "from_genre": from_genre,
        "to_genre": to_genre,
        "transition_type": transition_type,
        "success": success,
        "energy_delta": energy_delta,
        "bpm_delta": bpm_delta,
        "timestamp": datetime.utcnow().isoformat(),
    }
    recipes.append(recipe)
    
    # Keep last 50 recipes
    recipes = recipes[-50:]
    
    # Save
    await store.aput(("user", user_id, NAMESPACE_TRANSITION_RECIPES), "successful", recipes)


async def get_successful_recipes(
    user_id: str,
    from_genre: Optional[str] = None,
    to_genre: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get successful transition recipes for a user.
    
    Args:
        user_id: User ID
        from_genre: Optional filter by source genre
        to_genre: Optional filter by target genre
        
    Returns:
        List of successful recipe dicts
    """
    store = get_store()
    
    current_item = await store.aget(("user", user_id, NAMESPACE_TRANSITION_RECIPES), "successful")
    recipes = []
    if current_item:
        recipes = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(recipes, list):
            recipes = []
    
    # Filter to successful only
    successful = [r for r in recipes if r.get("success", False)]
    
    # Apply genre filters
    if from_genre:
        from_lower = from_genre.lower()
        successful = [r for r in successful if r.get("from_genre", "").lower() == from_lower]
    
    if to_genre:
        to_lower = to_genre.lower()
        successful = [r for r in successful if r.get("to_genre", "").lower() == to_lower]
    
    return successful


async def clear_user_memory(user_id: str) -> None:
    """
    Clear all memory for a user.
    
    Use with caution - this removes all learned preferences.
    """
    store = get_store()
    
    try:
        await store.adelete(("user", user_id, NAMESPACE_TASTE), "preferences")
        await store.adelete(("user", user_id, NAMESPACE_BANTER), "constraints")
        await store.adelete(("user", user_id, NAMESPACE_SESSION_SUMMARIES), "recent")
        await store.adelete(("user", user_id, NAMESPACE_TRANSITION_RECIPES), "successful")
        
        logger.info(f"Cleared all memory for user {user_id}")
    except Exception as e:
        logger.error(f"Error clearing user memory: {e}")


# =============================================================================
# Training Memory Updates
# =============================================================================

async def record_feedback_to_memory(
    user_id: str,
    feedback_type: str,  # "like", "dislike", "skip"
    track_artist: str,
    track_title: str,
    track_genres: List[str],
) -> None:
    """
    Record feedback event to long-term memory.
    
    Updates taste preferences based on feedback:
    - Like: Boost artist and genres
    - Dislike: Demote artist and genres
    - Skip: Slight demotion
    """
    updates = {}
    
    if feedback_type == "like":
        # Boost artist preference
        updates[f"artist:{track_artist.lower()}"] = 0.3
        # Boost genre preferences
        for genre in track_genres:
            updates[f"genre:{genre.lower()}"] = 0.15
        updates["overall_satisfaction"] = 0.1
        
    elif feedback_type == "dislike":
        # Demote artist preference
        updates[f"artist:{track_artist.lower()}"] = -0.4
        # Demote genre preferences (less than artist)
        for genre in track_genres:
            updates[f"genre:{genre.lower()}"] = -0.1
        updates["overall_satisfaction"] = -0.15
        
    elif feedback_type == "skip":
        # Slight demotion
        updates[f"artist:{track_artist.lower()}"] = -0.1
        # Don't demote genres for skip (might just be wrong time)
    
    if updates:
        await update_taste_preferences(user_id, updates)


async def record_training_outcome(
    user_id: str,
    mood_id: str,
    training_decision: Dict[str, Any],
) -> None:
    """
    Record a training decision to memory for future reference.
    
    This helps track what adjustments have been made to moods.
    """
    store = get_store()
    
    # Store under mood-specific namespace
    namespace = f"training_{mood_id}"
    
    # Load existing training history
    current_item = await store.aget(("user", user_id, namespace), "history")
    history = []
    if current_item:
        history = current_item.value if hasattr(current_item, "value") else current_item
        if not isinstance(history, list):
            history = []
    
    # Add new decision
    training_decision["timestamp"] = datetime.utcnow().isoformat()
    history.append(training_decision)
    
    # Keep last 100 training decisions per mood
    history = history[-100:]
    
    await store.aput(("user", user_id, namespace), "history", history)
